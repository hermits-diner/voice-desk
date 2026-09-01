"""1단계 검증: VibeVoice-1.5B 로 다화자 대화 wav 를 만들고 VRAM/소요시간을 기록한다.

지침 제약:
  - flash-attn 설치 금지 -> attn_implementation="sdpa" 고정
  - 경로에 한글/공백 금지 -> 전부 C:\ai 아래
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
from vibevoice.modular.modeling_vibevoice_inference import (
    VibeVoiceForConditionalGenerationInference,
)
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor

MODEL_DIR = Path(r"C:\ai\models\VibeVoice-1.5B")
VOICES_DIR = Path(r"C:\ai\voice-desk\backend\third_party\VibeVoice\demo\voices")
OUT_DIR = Path(r"C:\ai\voice-desk\backend\outputs")
SAMPLE_RATE = 24000

# 화자 2명 대화. VibeVoice 는 "Speaker N: 텍스트" 한 덩어리를 한 번에 렌더한다.
SCRIPT_2P = """Speaker 1: So I finally got around to testing the new setup last night, and honestly? I was not expecting it to go that smoothly.
Speaker 2: Really. Because last time you said the exact same thing, and then you spent six hours debugging a driver issue.
Speaker 1: Okay, that is fair. But this time I actually read the documentation first, which apparently is a novel strategy.
Speaker 2: Groundbreaking. Truly. So what changed?
Speaker 1: The big one was memory. I stopped loading both models at the same time. Turns out you do not need twenty gigabytes of weights sitting around when you are only using one of them.
Speaker 2: That does sound obvious in hindsight.
Speaker 1: Most good ideas do. Anyway, generation time dropped by about a third, and the output is cleaner.
Speaker 2: Alright, I am convinced. Send me the config and I will try it on mine this weekend."""


def gb(x: int) -> float:
    return round(x / 1024 ** 3, 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speakers", nargs="+",
                    default=["en-Alice_woman", "en-Carter_man"])
    ap.add_argument("--cfg-scale", type=float, default=1.3)
    ap.add_argument("--ddpm-steps", type=int, default=10)
    ap.add_argument("--out", default="verify_2p.wav")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    voice_paths = [str(VOICES_DIR / f"{n}.wav") for n in args.speakers]
    for p in voice_paths:
        if not os.path.exists(p):
            raise SystemExit(f"보이스 파일 없음: {p}")

    torch.cuda.reset_peak_memory_stats()
    base_vram = torch.cuda.memory_allocated()
    print(f"[env] torch {torch.__version__}  cuda {torch.version.cuda}")
    print(f"[env] device {torch.cuda.get_device_name(0)}")

    t0 = time.time()
    processor = VibeVoiceProcessor.from_pretrained(str(MODEL_DIR))
    model = VibeVoiceForConditionalGenerationInference.from_pretrained(
        str(MODEL_DIR),
        torch_dtype=torch.bfloat16,
        device_map="cuda",
        attn_implementation="sdpa",   # flash-attn 금지 제약
    )
    model.eval()
    model.set_ddpm_inference_steps(num_steps=args.ddpm_steps)
    load_s = time.time() - t0
    vram_after_load = torch.cuda.memory_allocated()
    attn = model.model.language_model.config._attn_implementation
    print(f"[load] {load_s:.1f}s   attn={attn}   "
          f"VRAM {gb(vram_after_load - base_vram)} GB")
    if attn != "sdpa":
        raise SystemExit(f"attn_implementation 이 sdpa 가 아님: {attn}")

    inputs = processor(
        text=[SCRIPT_2P],
        voice_samples=[voice_paths],
        padding=True,
        return_tensors="pt",
        return_attention_mask=True,
    )
    inputs = {k: (v.to("cuda") if torch.is_tensor(v) else v)
              for k, v in inputs.items()}
    in_tokens = inputs["input_ids"].shape[1]

    torch.cuda.reset_peak_memory_stats()
    t1 = time.time()
    out = model.generate(
        **inputs,
        max_new_tokens=None,
        cfg_scale=args.cfg_scale,
        tokenizer=processor.tokenizer,
        generation_config={"do_sample": False},
        verbose=False,
        is_prefill=True,
    )
    gen_s = time.time() - t1
    peak_vram = torch.cuda.max_memory_allocated()

    audio = out.speech_outputs[0]
    n_samples = audio.shape[-1]
    dur = n_samples / SAMPLE_RATE
    out_path = OUT_DIR / args.out
    processor.save_audio(audio, output_path=str(out_path))

    report = {
        "engine": "vibevoice-1.5b",
        "attn_implementation": attn,
        "dtype": "bfloat16",
        "speakers": args.speakers,
        "cfg_scale": args.cfg_scale,
        "ddpm_steps": args.ddpm_steps,
        "load_seconds": round(load_s, 1),
        "vram_after_load_gb": gb(vram_after_load - base_vram),
        "vram_peak_gb": gb(peak_vram),
        "input_tokens": int(in_tokens),
        "generated_tokens": int(out.sequences.shape[1] - in_tokens),
        "generation_seconds": round(gen_s, 1),
        "audio_seconds": round(dur, 2),
        "rtf": round(gen_s / dur, 3) if dur else None,
        "output_wav": str(out_path),
        "wav_bytes": out_path.stat().st_size,
    }
    print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
    (OUT_DIR / "verify_vibevoice_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
