"""발화 뒤에 따라붙는 금속성 톤(4~6kHz 협대역)을 조건별로 계측한다.

금속 프레임 정의: 50ms 창에서
  - 지배 주파수 3.5~9kHz (모음 300~700Hz, 마찰음은 광대역이라 톤성이 낮다)
  - 톤성(피크/중앙값) > 20dB  ← 좁은 톤
  - RMS -55~-22dBFS           ← 무음도 본발화도 아닌 '딸려오는' 소리
"""
from __future__ import annotations

import os

os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import torch
from vibevoice.modular.modeling_vibevoice_inference import (
    VibeVoiceForConditionalGenerationInference,
)
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor

MODEL = r"C:\ai\models\VibeVoice-1.5B"
V = r"C:\ai\voice-desk\backend\third_party\VibeVoice\demo\voices"
OUT = r"C:\ai\voice-desk\backend\outputs"

SCRIPT = (
    "Speaker 1: So the quarterly numbers came in this morning. Better than we hoped.\n"
    "Speaker 2: That is a relief. The board meeting should be easy then.\n"
    "Speaker 1: Mostly. There is still the question of the marketing budget.\n"
    "Speaker 2: There always is. Send me the summary and I will look tonight."
)


def metallic_score(x: np.ndarray, sr: int) -> tuple[int, int, list[float]]:
    win = int(sr * 0.05)
    hits: list[float] = []
    total = 0
    for i in range(0, len(x) - win, win):
        seg = x[i:i + win]
        total += 1
        rms = 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-12)
        if not -55 <= rms <= -22:
            continue
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs = np.fft.rfftfreq(len(seg), 1 / sr)
        b = freqs >= 300
        pk = int(np.argmax(spec[b]))
        ton = 20 * np.log10((spec[b][pk] + 1e-12) / (np.median(spec[b]) + 1e-12))
        if 3500 <= freqs[b][pk] <= 9000 and ton > 20:
            hits.append(i / sr)
    return len(hits), total, hits


def main() -> None:
    proc = VibeVoiceProcessor.from_pretrained(MODEL)
    model = VibeVoiceForConditionalGenerationInference.from_pretrained(
        MODEL, torch_dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa",
    )
    model.eval()
    tok = proc.tokenizer

    cases = [
        ("ddpm10 · Alice+Carter", 10, ["en-Alice_woman", "en-Carter_man"]),
        ("ddpm20 · Alice+Carter", 20, ["en-Alice_woman", "en-Carter_man"]),
        ("ddpm30 · Alice+Carter", 30, ["en-Alice_woman", "en-Carter_man"]),
        ("ddpm10 · Maya+Frank  ", 10, ["en-Maya_woman", "en-Frank_man"]),
        ("ddpm20 · Maya+Frank  ", 20, ["en-Maya_woman", "en-Frank_man"]),
    ]
    for label, steps, voices in cases:
        model.set_ddpm_inference_steps(num_steps=steps)
        inputs = proc(
            text=[SCRIPT],
            voice_samples=[[f"{V}\\{v}.wav" for v in voices]],
            padding=True, return_tensors="pt", return_attention_mask=True,
        )
        inputs = {k: (v.to("cuda") if torch.is_tensor(v) else v) for k, v in inputs.items()}
        torch.manual_seed(1234)
        torch.cuda.manual_seed_all(1234)
        out = model.generate(
            **inputs, max_new_tokens=None, cfg_scale=1.3, tokenizer=tok,
            generation_config={"do_sample": False}, verbose=False, is_prefill=True,
        )
        x = out.speech_outputs[0].detach().to(torch.float32).cpu().numpy().reshape(-1)
        n_hits, total, hits = metallic_score(x, 24000)
        dur = len(x) / 24000
        fname = f"diag_metal_{steps}_{voices[0].split('-')[1].split('_')[0]}.wav"
        import soundfile as sf
        sf.write(f"{OUT}\\{fname}", x, 24000, subtype="PCM_16")
        where = " ".join(f"{h:.1f}" for h in hits[:8])
        print(f"{label}  {dur:6.2f}s  금속 프레임 {n_hits:3d}/{total}  위치(s): {where}",
              flush=True)


if __name__ == "__main__":
    main()
