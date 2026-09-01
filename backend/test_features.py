"""신기능 스모크: 번역 렌더 + SRT + Anki + PCM 스트림 + Supertonic 렌더."""
import json, sys, time
from pathlib import Path
import requests

B = "http://127.0.0.1:7861"

def wait(jid, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = requests.get(f"{B}/jobs/{jid}", timeout=30).json()
        if s["state"] in ("done", "error", "cancelled"):
            return s
        time.sleep(1.5)
    raise TimeoutError

ok = True

# 1) Supertonic 한국어 대화 + 번역 필드 + SRT
script = {
    "title": "한국어 기능 점검",
    "format": "Conversation",
    "segments": [
        {"speaker": "A", "text": "이번 주말에 계획 있어?", "note": None, "translation": None},
        {"speaker": "B", "text": "북한산에 단풍 보러 가려고. 같이 갈래?", "note": None, "translation": None},
        {"speaker": "A", "text": "좋지. 오전 9시에 우이역에서 만나자.", "note": None, "translation": None},
    ],
}
r = requests.post(f"{B}/render", json={
    "script": script, "engine": "supertonic",
    "voices": [{"speaker": "A", "voice": "st-F1"}, {"speaker": "B", "voice": "st-M2"}],
}, timeout=30).json()
jid = r["id"]

# PCM 스트림도 이 작업으로 확인
time.sleep(2.0)
pcm = requests.get(f"{B}/jobs/{jid}/pcm?from_byte=0", timeout=30)
print("PCM 헤더:", pcm.headers.get("X-Pcm-Sr"), "Hz, bytes:", len(pcm.content), "state:", pcm.headers.get("X-Job-State"))

s = wait(jid)
print("Supertonic 렌더:", s["state"], s.get("duration"), "s")
ok &= s["state"] == "done"
audio = s["audio_path"]
base = audio.rsplit(".", 1)[0]
srt = Path(base + ".srt")
print("SRT:", srt.exists(), "|", srt.name if srt.exists() else "")
ok &= srt.exists()
if srt.exists():
    print(srt.read_text("utf-8-sig")[:200].replace("\n", " / "))

# 2) Anki 내보내기
r2 = requests.post(f"{B}/export/anki", json={
    "audio_path": audio, "title": script["title"], "timings": s["timings"],
}, timeout=120)
print("Anki:", r2.status_code, r2.json() if r2.ok else r2.text[:150])
ok &= r2.ok

# 3) /jobs 목록
lst = requests.get(f"{B}/jobs", timeout=30).json()
print("/jobs 최근:", len(lst), "건, 첫 항목 state:", lst[0]["state"] if lst else "-")

# 4) 보이스 프리뷰 캐시 (supertonic — GPU 불필요)
t0 = time.time()
p1 = requests.get(f"{B}/voices/st-F3/preview", timeout=300)
t1 = time.time() - t0
t0 = time.time()
p2 = requests.get(f"{B}/voices/st-F3/preview", timeout=30)
t2 = time.time() - t0
print(f"프리뷰: 첫 {t1:.1f}s({p1.status_code}) -> 캐시 {t2:.2f}s({p2.status_code})")
ok &= p1.ok and p2.ok and t2 < 1.0

print("\n전체:", "통과" if ok else "실패")
sys.exit(0 if ok else 1)
