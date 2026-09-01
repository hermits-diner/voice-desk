"""보충 검증: 아라비아 숫자·단위·영어 약어가 섞인 현실적 문장을 제대로 읽는가."""
import os
os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")
import numpy as np, librosa, sys
sys.path.insert(0, r"C:\ai\voice-desk\backend")
from verify_korean import cer, norm

SENTS = [
    "회의는 오후 3시 반에 시작해서 5시쯤 끝날 예정입니다.",
    "이 노트북은 128기가바이트 메모리를 지원합니다.",
    "9월 1일 월요일부터 새로운 학기가 시작됩니다.",
    "택배가 2026년 9월 3일에 도착한다고 합니다.",
    "가격은 45,000원이고 배송비는 3,000원입니다.",
    "제 전화번호는 010-1234-5678입니다.",
]

from supertonic import TTS
import whisper
tts = TTS(model="supertonic-3", model_dir=r"C:\ai\models\supertonic-3", auto_download=False)
style = tts.get_voice_style("F1")
asr = whisper.load_model("large-v3", device="cuda", download_root=r"C:\ai\models\whisper")

errs = []
for s in SENTS:
    wav, _ = tts.synthesize(s, style, lang="ko")
    a16 = librosa.resample(np.asarray(wav, np.float32).reshape(-1), orig_sr=44100, target_sr=16000)
    hyp = (asr.transcribe(a16, language="ko", fp16=True).get("text") or "").strip()
    e = cer(s, hyp)
    errs.append(e)
    print(f"CER {e*100:5.1f}%  입력: {s}")
    print(f"            전사: {hyp}")
print(f"\n숫자 표기 입력 평균 CER: {np.mean(errs)*100:.2f}%")
