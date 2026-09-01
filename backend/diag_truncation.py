"""410단어 대본이 50초로 잘린 원인을 격리한다.

비교 조건
  A) audio_streamer 없이            <- CLI 검증과 같은 조건
  B) audio_streamer 전달 (앱 경로)
  C) max_length_times 를 키워서
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
from vibevoice.modular.modeling_vibevoice_inference import (
    VibeVoiceForConditionalGenerationInference,
)
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor

from app.engines.vibevoice_engine import build_prompt
from app.schemas import Script

MODEL = r"C:\ai\models\VibeVoice-1.5B"
VOICES = r"C:\ai\voice-desk\backend\third_party\VibeVoice\demo\voices"
TIMING = Path(
    r"C:\Users\오정훈\Music\VoiceDesk\20260901_Fixing Old Code or Starting Fresh_Conversation.json"
)


class Streamer:
    """앱이 쓰는 진행률 스트리머와 같은 구조."""

    def __init__(self) -> None:
        self.finished_flags = [False]
        self.frames = 0

    def put(self, chunks, idx) -> None:  # noqa: ANN001
        self.frames += 1

    def end(self, idx=None) -> None:  # noqa: ANN001
        self.finished_flags[0] = True


def load_script() -> Script:
    d = json.loads(TIMING.read_text("utf-8"))
    return Script(
        title=d["title"], format=d["format"],
        segments=[{"speaker": s["speaker"], "text": s["text"], "note": None}
                  for s in d["segments"]],
    )


def main() -> None:
    script = load_script()
    prompt = build_prompt(script)
    words = sum(len(s.text.split()) for s in script.segments)
    print(f"세그먼트 {len(script.segments)}개 · {words}단어")
    print(f"정상 속도(2.5단어/초) 기준 예상 {words / 2.5:.0f}초\n")

    proc = VibeVoiceProcessor.from_pretrained(MODEL)
    model = VibeVoiceForConditionalGenerationInference.from_pretrained(
        MODEL, torch_dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa",
    )
    model.eval()
    model.set_ddpm_inference_steps(num_steps=10)
    tok = proc.tokenizer

    inputs = proc(
        text=[prompt],
        voice_samples=[[f"{VOICES}\\en-Alice_woman.wav", f"{VOICES}\\en-Carter_man.wav"]],
        padding=True, return_tensors="pt", return_attention_mask=True,
    )
    inputs = {k: (v.to("cuda") if torch.is_tensor(v) else v) for k, v in inputs.items()}
    n_in = int(inputs["input_ids"].shape[1])
    print(f"입력 토큰 {n_in}")
    print(f"max_length_times=2 이면 상한 {2 * n_in} 스텝 = {2 * n_in * 3200 / 24000:.0f}초")
    print(f"max_length_times=4 이면 상한 {4 * n_in} 스텝 = {4 * n_in * 3200 / 24000:.0f}초\n")

    cases = [
        ("A) 스트리머 없음", {}, None),
        ("B) 스트리머 전달", {}, Streamer()),
        ("C) max_length_times=4", {"max_length_times": 4}, None),
    ]
    for label, extra, streamer in cases:
        torch.manual_seed(1234)
        kw = dict(
            max_new_tokens=None, cfg_scale=1.3, tokenizer=tok,
            generation_config={"do_sample": False}, verbose=False, is_prefill=True,
        )
        kw.update(extra)
        if streamer is not None:
            kw["audio_streamer"] = streamer
        out = model.generate(**inputs, **kw)
        audio = out.speech_outputs[0]
        n = audio.shape[-1]
        gen = out.sequences[0].tolist()[n_in:]
        diff = sum(1 for t in gen if t == tok.speech_diffusion_id)
        ends = sum(1 for t in gen if t == tok.speech_end_id)
        reached = bool(out.reach_max_step_sample[0]) if out.reach_max_step_sample is not None else None
        print(f"{label:24s} {n / 24000:7.2f}s  생성토큰 {len(gen):5d}  "
              f"확산 {diff:5d}  END {ends:3d}  상한도달={reached}")


if __name__ == "__main__":
    main()
