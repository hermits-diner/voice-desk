"""2단계 검증: Dia2-2B 로 2인 대화 wav 를 만들고 VRAM/소요시간을 기록한다.

확인 항목
  - 로컬 경로만으로 오프라인 로드가 되는가 (weights / tokenizer / mimi)
  - 2분 상한(max_context_steps=1500 @ 12.5Hz)이 실제로 어떻게 걸리는가
  - (laughs) 같은 비언어 표기가 먹히는가  -> --nonverbal
  - 레퍼런스 프리픽스(클로닝)가 Windows 에서 도는가 -> --prefix
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")

import torch

from dia2.engine import Dia2
from dia2.generation import build_generation_config, validate_generation_params

WEIGHTS = Path(r"C:\ai\models\Dia2-2B")
MIMI = Path(r"C:\ai\models\mimi")
OUT_DIR = Path(r"C:\ai\voice-desk\backend\outputs")
DIA2_SRC = Path(r"C:\ai\voice-desk\backend\third_party\dia2")

PLAIN = (
    "[S1] So I finally tested the new setup last night, and it went a lot "
    "smoother than I expected. [S2] Really? Last time you said that, you spent "
    "six hours chasing a driver bug. [S1] That is fair. This time I read the "
    "documentation first, which is apparently a novel strategy. [S2] "
    "Groundbreaking. So what actually changed? [S1] Memory, mostly. I stopped "
    "loading both models at once. [S2] Alright, send me the config and I will "
    "try it this weekend."
)

NONVERBAL = (
    "[S1] Wait, you actually read the manual? (laughs) [S2] I know, I know. "
    "(clears throat) It was a moment of weakness. [S1] (laughs) That explains "
    "why it worked for once. [S2] Hey, that is uncalled for."
)


def gb(x: int) -> float:
    return round(x / 1024 ** 3, 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nonverbal", action="store_true",
                    help="(laughs) 등 비언어 표기 대본으로 테스트")
    ap.add_argument("--prefix", action="store_true",
                    help="레퍼런스 오디오 프리픽스(클로닝) 경로 테스트")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--topk", type=int, default=50)
    ap.add_argument("--cfg", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--no-cuda-graph", action="store_true",
                    help="CUDA 그래프 캡처를 끈다 (Windows 에서 4배 느려진다)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    script = NONVERBAL if args.nonverbal else PLAIN
    tag = "nonverbal" if args.nonverbal else ("prefix" if args.prefix else "plain")
    out_path = OUT_DIR / (args.out or f"verify_dia2_{tag}.wav")

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    torch.cuda.reset_peak_memory_stats()
    base = torch.cuda.memory_allocated()
    print(f"[env] torch {torch.__version__}  cuda {torch.version.cuda}")

    t0 = time.time()
    dia = Dia2.from_local(
        config_path=str(WEIGHTS / "config.json"),
        weights_path=str(WEIGHTS / "model.safetensors"),
        tokenizer_id=str(WEIGHTS),   # 로컬 토크나이저
        mimi_id=str(MIMI),           # 로컬 Mimi 코덱
        device="cuda",
        dtype="bfloat16",
    )
    temperature, top_k, cfg_scale = validate_generation_params(
        temperature=args.temperature, top_k=args.topk, cfg_scale=args.cfg
    )
    cfg = build_generation_config(
        temperature=temperature, top_k=top_k, cfg_scale=cfg_scale
    )

    # Windows(WDDM) 에서는 커널 런치 오버헤드가 지배적이라 CUDA 그래프가 RTF 를
    # 4.87 -> 1.23 으로 줄인다. 기본으로 켠다.
    overrides = {"use_cuda_graph": not args.no_cuda_graph}
    if args.prefix:
        overrides["prefix_speaker_1"] = str(DIA2_SRC / "example_prefix1.wav")
        overrides["prefix_speaker_2"] = str(DIA2_SRC / "example_prefix2.wav")

    t1 = time.time()
    result = dia.generate(
        script,
        config=cfg,
        output_wav=str(out_path),
        verbose=True,
        **overrides,
    )
    gen_s = time.time() - t1
    load_s = t1 - t0
    peak = torch.cuda.max_memory_allocated()
    resident = torch.cuda.memory_allocated()

    import soundfile as sf
    info = sf.info(str(out_path))
    dur = info.frames / info.samplerate

    report = {
        "engine": "dia2-2b",
        "dtype": "bfloat16",
        "script_kind": tag,
        "cuda_graph": not args.no_cuda_graph,
        "temperature": temperature,
        "top_k": top_k,
        "cfg_scale": cfg_scale,
        "seed": args.seed,
        "load_seconds": round(load_s, 1),
        "generation_seconds": round(gen_s, 1),
        "vram_resident_gb": gb(resident - base),
        "vram_peak_gb": gb(peak),
        "audio_seconds": round(dur, 2),
        "sample_rate": info.samplerate,
        "rtf": round(gen_s / dur, 3) if dur else None,
        "output_wav": str(out_path),
    }
    print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
    (OUT_DIR / f"verify_dia2_{tag}_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
