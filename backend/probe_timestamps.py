"""VibeVoice 토큰 열에서 세그먼트 경계를 뽑을 수 있는지 확인한다.

확인할 것
  1. 확산 토큰 1개 == 3200 샘플(24kHz / 7.5Hz) 이 정확한가
  2. 화자 전환마다 speech_start / speech_end 마커가 나오는가
     -> 나오면 토큰 열만으로 세그먼트 타임스탬프를 만들 수 있다
     -> 안 나오면 다른 방법을 찾아야 한다
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

MODEL_DIR = r"C:\ai\models\VibeVoice-1.5B"
VOICES = r"C:\ai\voice-desk\backend\third_party\VibeVoice\demo\voices"

# 턴 4개, 길이를 일부러 다르게 해서 경계가 맞는지 눈으로 볼 수 있게 한다.
SCRIPT = (
    "Speaker 1: One.\n"
    "Speaker 2: Two, and this one is deliberately quite a bit longer so the "
    "segment boundary is easy to spot in the timings.\n"
    "Speaker 1: Three.\n"
    "Speaker 2: Four, also fairly long, trailing the conversation out to the end."
)

processor = VibeVoiceProcessor.from_pretrained(MODEL_DIR)
model = VibeVoiceForConditionalGenerationInference.from_pretrained(
    MODEL_DIR, torch_dtype=torch.bfloat16, device_map="cuda",
    attn_implementation="sdpa",
)
model.eval()
model.set_ddpm_inference_steps(num_steps=10)

tok = processor.tokenizer
START, END, DIFF = tok.speech_start_id, tok.speech_end_id, tok.speech_diffusion_id
print(f"speech_start_id={START}  speech_end_id={END}  speech_diffusion_id={DIFF}")

inputs = processor(
    text=[SCRIPT],
    voice_samples=[[f"{VOICES}\\en-Alice_woman.wav", f"{VOICES}\\en-Carter_man.wav"]],
    padding=True, return_tensors="pt", return_attention_mask=True,
)
inputs = {k: (v.to("cuda") if torch.is_tensor(v) else v) for k, v in inputs.items()}
n_in = inputs["input_ids"].shape[1]

out = model.generate(
    **inputs, max_new_tokens=None, cfg_scale=1.3, tokenizer=tok,
    generation_config={"do_sample": False}, verbose=False, is_prefill=True,
)

seq = out.sequences[0].tolist()
gen = seq[n_in:]
audio = out.speech_outputs[0]
n_samples = audio.shape[-1]

print(f"\n입력 토큰 {n_in} / 생성 토큰 {len(gen)}")
print(f"오디오 샘플 {n_samples}  =  {n_samples / 24000:.3f} s")

counts = Counter(gen)
n_diff = counts[DIFF]
n_start = counts[START]
n_end = counts[END]
print(f"\n생성 토큰 구성: diffusion={n_diff}  start={n_start}  end={n_end}  기타={len(gen) - n_diff - n_start - n_end}")

print("\n[검증 1] 확산 토큰 x 3200 == 샘플 수 ?")
print(f"  {n_diff} x 3200 = {n_diff * 3200}   실제 {n_samples}   차이 {n_samples - n_diff * 3200}")

print("\n[검증 2] 화자 전환마다 마커가 있는가 ? (턴 4개)")
print(f"  speech_start 개수 = {n_start}   speech_end 개수 = {n_end}")

# 생성 구간에서 특수 토큰이 나온 위치와, 그 앞까지 누적된 확산 토큰 수
marks = []
acc = 0
for i, t in enumerate(gen):
    if t == DIFF:
        acc += 1
    elif t in (START, END):
        name = "START" if t == START else "END"
        marks.append((i, name, acc, acc * 3200 / 24000))
print("\n  위치(생성 인덱스) / 종류 / 그때까지 확산토큰 / 초")
for m in marks[:40]:
    print(f"    {m[0]:5d}  {m[1]:<6s} {m[2]:5d}  {m[3]:8.3f}s")
if not marks:
    print("    (특수 토큰 없음 -- 전체가 한 덩어리로 생성됨)")

# 기타 토큰(텍스트 토큰)이 섞여 있으면 그것도 확인
other = [(i, t) for i, t in enumerate(gen) if t not in (DIFF, START, END)]
print(f"\n  기타 토큰 {len(other)}개")
for i, t in other[:20]:
    print(f"    {i:5d}  id={t:<8d} {tok.decode([t])!r}")
