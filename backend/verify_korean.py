"""Supertonic 한국어 성능 검증.

사용자 지시: "한국어는 성능이 검증된 것만 써."

방법: 성격이 다른 한국어 문장 10개를 합성하고 whisper-large-v3 로 재전사해
CER(문자 오류율)을 잰다. 공백·문장부호를 제거한 자모 수준이 아닌 음절 문자열로
편집거리를 계산한다. 숫자는 표기 차이(구월/9월)가 CER 에 잡힐 수 있어
문장별 결과를 그대로 보고한다. 최종 판정은 청취 샘플로 사용자가 한다.
"""
from __future__ import annotations

import os
import re
import time

os.environ.setdefault("HF_HOME", r"C:\ai\models\hf-cache")

import numpy as np

SENTENCES = [
    ("일상", "어제 시장에서 사 온 과일이 생각보다 훨씬 달아서 놀랐어요."),
    ("일상", "다음 주에 이사를 가야 해서 요즘 짐을 조금씩 정리하고 있습니다."),
    ("숫자", "회의는 오후 세 시 반에 시작해서 다섯 시쯤 끝날 예정입니다."),
    ("숫자", "이 노트북은 백이십팔 기가바이트 메모리를 지원합니다."),
    ("날짜", "구월 일일 월요일부터 새로운 학기가 시작됩니다."),
    ("영어혼용", "요즘 인공지능 스타트업들이 오픈소스 모델을 많이 공개하고 있어요."),
    ("영어혼용", "커피 한 잔 마시면서 팟캐스트를 듣는 게 아침 루틴이에요."),
    ("긴문장", "처음에는 조금 어색했지만, 매일 십 분씩 꾸준히 연습하다 보니 어느새 발음이 자연스러워지고 자신감도 붙기 시작했습니다."),
    ("질문", "혹시 이 근처에 조용히 공부할 만한 카페가 있을까요?"),
    ("감탄", "와, 이 경치 좀 보세요. 정말 그림 같지 않나요?"),
]

PARAGRAPH = (
    "안녕하세요, 보이스데스크 한국어 시험 낭독입니다. "
    "오늘은 발음의 자연스러움과 억양, 그리고 숫자 읽기를 확인합니다. "
    "예를 들어 오후 세 시 반, 백이십팔 기가바이트, 이런 표현들이 잘 들리는지요. "
    "마지막으로 질문 억양도 한번 볼까요? 이 정도면 쓸 만하다고 느껴지시나요?"
)


def norm(s: str) -> str:
    return re.sub(r"[\s.,!?~'\"‘’“”·…()\[\]-]", "", s)


def cer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    if not r:
        return 0.0
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=np.int32)
    d[:, 0] = np.arange(len(r) + 1)
    d[0, :] = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            c = 0 if r[i - 1] == h[j - 1] else 1
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + c)
    return float(d[-1, -1]) / len(r)


def main() -> None:
    from supertonic import TTS

    import whisper

    print("Supertonic 로드...", flush=True)
    tts = TTS(model="supertonic-3", model_dir=r"C:\ai\models\supertonic-3",
              auto_download=False)
    styles = {"F1": tts.get_voice_style("F1"), "M2": tts.get_voice_style("M2")}

    print("whisper large-v3 로드 (cuda)...", flush=True)
    t0 = time.time()
    asr = whisper.load_model("large-v3", device="cuda",
                             download_root=r"C:\ai\models\whisper")
    print(f"  {time.time()-t0:.1f}s", flush=True)

    import soundfile as sf

    results = []
    for i, (kind, sent) in enumerate(SENTENCES):
        sid = "F1" if i % 2 == 0 else "M2"
        t1 = time.time()
        wav, _ = tts.synthesize(sent, styles[sid], lang="ko")
        synth_s = time.time() - t1
        wav = np.asarray(wav, dtype=np.float32).reshape(-1)
        # whisper 는 경로를 주면 PATH 의 ffmpeg 를 부르므로 16kHz 배열로 직접 준다
        import librosa

        a16 = librosa.resample(wav, orig_sr=44100, target_sr=16000)
        out = asr.transcribe(a16, language="ko", fp16=True)
        hyp = (out.get("text") or "").strip()
        e = cer(sent, hyp)
        results.append((kind, sid, sent, hyp, e, synth_s, len(wav) / 44100))
        print(f"[{kind:5s}·{sid}] CER {e*100:5.1f}%  ({len(wav)/44100:4.1f}s 오디오/{synth_s:4.1f}s 합성)")
        print(f"   입력: {sent}")
        print(f"   전사: {hyp}", flush=True)

    mean_cer = float(np.mean([r[4] for r in results]))
    worst = max(results, key=lambda r: r[4])
    print(f"\n평균 CER: {mean_cer*100:.2f}%   최악: {worst[4]*100:.1f}% ({worst[0]})")
    print("판정 기준: 평균 5% 이하 + 최악 12% 이하이면 통과 (숫자 표기 차이 감안)")
    ok = mean_cer <= 0.05 and worst[4] <= 0.12
    print("결과:", "통과" if ok else "미달")

    # 청취 샘플 두 개 (여성 F1, 남성 M2)
    for sid in ("F1", "M2"):
        wav, _ = tts.synthesize(PARAGRAPH, styles[sid], lang="ko")
        wav = np.asarray(wav, dtype=np.float32).reshape(-1)
        p = rf"C:\Users\오정훈\Music\VoiceDesk\한국어검증_Supertonic_{sid}.wav"
        sf.write(p, wav, 44100, subtype="PCM_16")
        print("청취 샘플:", p)


if __name__ == "__main__":
    main()
