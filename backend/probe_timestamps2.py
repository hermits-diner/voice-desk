"""왜 실제 대본에서 END 마커 수가 세그먼트 수와 안 맞는지 확인한다.

가설: 같은 화자가 연속되면 VibeVoice 가 턴을 하나로 합친다.
"""
from __future__ import annotations

import os
from collections import Counter

os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
from vibevoice.modular.modeling_vibevoice_inference import (
    VibeVoiceForConditionalGenerationInference,
)
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor

MODEL = r"C:\ai\models\VibeVoice-1.5B"
VOICES = r"C:\ai\voice-desk\backend\third_party\VibeVoice\demo\voices"

CASES = {
    "A: 화자 교대 4턴": (
        "Speaker 1: One two three.\n"
        "Speaker 2: Four five six seven eight.\n"
        "Speaker 1: Nine ten.\n"
        "Speaker 2: Eleven twelve thirteen."
    ),
    "B: 같은 화자 3턴 연속": (
        "Speaker 1: One two three.\n"
        "Speaker 1: Four five six seven eight.\n"
        "Speaker 1: Nine ten eleven."
    ),
    "C: 3인 교대 6턴": (
        "Speaker 1: One two three.\n"
        "Speaker 2: Four five six.\n"
        "Speaker 3: Seven eight nine.\n"
        "Speaker 1: Ten eleven.\n"
        "Speaker 2: Twelve thirteen.\n"
        "Speaker 3: Fourteen fifteen."
    ),
}

proc = VibeVoiceProcessor.from_pretrained(MODEL)
model = VibeVoiceForConditionalGenerationInference.from_pretrained(
    MODEL, torch_dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa",
)
model.eval()
model.set_ddpm_inference_steps(num_steps=10)
tok = proc.tokenizer
START, END, DIFF = tok.speech_start_id, tok.speech_end_id, tok.speech_diffusion_id

VOICE_FILES = [
    f"{VOICES}\\en-Alice_woman.wav",
    f"{VOICES}\\en-Carter_man.wav",
    f"{VOICES}\\en-Frank_man.wav",
]

for name, script in CASES.items():
    n_turns = len([l for l in script.splitlines() if l.strip()])
    n_speakers = len({l.split(":")[0] for l in script.splitlines() if l.strip()})
    inputs = proc(
        text=[script], voice_samples=[VOICE_FILES[:n_speakers]],
        padding=True, return_tensors="pt", return_attention_mask=True,
    )
    inputs = {k: (v.to("cuda") if torch.is_tensor(v) else v) for k, v in inputs.items()}
    n_in = inputs["input_ids"].shape[1]
    torch.manual_seed(1234)
    out = model.generate(
        **inputs, max_new_tokens=None, cfg_scale=1.3, tokenizer=tok,
        generation_config={"do_sample": False}, verbose=False, is_prefill=True,
    )
    gen = out.sequences[0].tolist()[n_in:]
    c = Counter(gen)
    n_samples = out.speech_outputs[0].shape[-1]

    ends, acc = [], 0
    for t in gen:
        if t == DIFF:
            acc += 1
        elif t == END:
            ends.append(round(acc * 3200 / 24000, 3))

    print(f"\n=== {name} ===")
    print(f"  대본 턴 {n_turns}개 · 화자 {n_speakers}명")
    print(f"  diffusion={c[DIFF]}  START={c[START]}  END={c[END]}")
    print(f"  샘플 {n_samples} == diff*3200 {c[DIFF]*3200} ? {n_samples == c[DIFF]*3200}")
    print(f"  END 위치(초): {ends}")
    print(f"  전체 길이: {n_samples/24000:.3f}s")
    print(f"  >>> END 개수 {c[END]} vs 턴 {n_turns}  ->  {'일치' if c[END]==n_turns else '불일치'}")
