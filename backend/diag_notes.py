"""괄호 연기 지시가 생성 길이를 무너뜨리는지 확인한다."""
import json, os
os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import torch
from pathlib import Path
from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference
from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor
from app.engines.vibevoice_engine import build_prompt
from app.schemas import Script

MODEL = r"C:\ai\models\VibeVoice-1.5B"
V = r"C:\ai\voice-desk\backend\third_party\VibeVoice\demo\voices"
d = json.loads(Path(r"C:\Users\오정훈\Music\VoiceDesk\20260901_Fixing Old Code or Starting Fresh_Conversation.json").read_text("utf-8"))

# 실제 앱 렌더와 동일: 0번과 2번 세그먼트에 노트
notes = {0: "friendly, opening the conversation", 2: "thoughtful, gentle suggestion"}
segs = [{"speaker": s["speaker"], "text": s["text"], "note": notes.get(i)} for i, s in enumerate(d["segments"])]
script = Script(title=d["title"], format=d["format"], segments=segs)
prompt = build_prompt(script)
print("프롬프트 앞 220자:")
print(prompt[:220])
print()

proc = VibeVoiceProcessor.from_pretrained(MODEL)
model = VibeVoiceForConditionalGenerationInference.from_pretrained(
    MODEL, torch_dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa")
model.eval(); model.set_ddpm_inference_steps(num_steps=10)
tok = proc.tokenizer
inputs = proc(text=[prompt], voice_samples=[[f"{V}\en-Alice_woman.wav", f"{V}\en-Carter_man.wav"]],
              padding=True, return_tensors="pt", return_attention_mask=True)
inputs = {k: (v.to("cuda") if torch.is_tensor(v) else v) for k, v in inputs.items()}
n_in = inputs["input_ids"].shape[1]
torch.manual_seed(1234)
out = model.generate(**inputs, max_new_tokens=None, cfg_scale=1.3, tokenizer=tok,
                     generation_config={"do_sample": False}, verbose=False, is_prefill=True)
n = out.speech_outputs[0].shape[-1]
gen = out.sequences[0].tolist()[n_in:]
print(f"노트 포함: {n/24000:.2f}s  입력 {n_in}  생성 {len(gen)}  "
      f"END {sum(1 for t in gen if t == tok.speech_end_id)}")
