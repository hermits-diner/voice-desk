"""5분 이상 3인 대화 검증. Gemini 로 long 대본을 만들고 VibeVoice 로 렌더한다."""
import json, sys, time
import requests

B = "http://127.0.0.1:7861"

r = requests.post(f"{B}/script", json={
    "topic": "Three friends plan a two-week camping trip: routes, food, budget, and what could go wrong",
    "format": "Conversation", "length": "long", "level": "B1",
    "speakers": 3, "tone": "lively but relaxed",
}, timeout=300)
r.raise_for_status()
script = r.json()["script"]
words = sum(len(s["text"].split()) for s in script["segments"])
print(f"대본: {script['title']!r}  세그먼트 {len(script['segments'])}  단어 {words}", flush=True)

r = requests.post(f"{B}/render", json={"script": script, "engine": "vibevoice", "seed": 1234}, timeout=30)
r.raise_for_status()
jid = r.json()["id"]
print("job", jid, flush=True)
last = ""
while True:
    s = requests.get(f"{B}/jobs/{jid}", timeout=30).json()
    line = f"{s['state']} {s['progress']*100:.0f}% {s['elapsed']:.0f}s {s['message']}"
    if line != last:
        print(line, flush=True); last = line
    if s["state"] in ("done", "error", "cancelled"):
        break
    time.sleep(5)
print(json.dumps({k: s[k] for k in ("state","duration","audio_path","timing_path","error")}, ensure_ascii=False, indent=2))
if s["state"] == "done":
    print(f"단어/초: {words/s['duration']:.2f}")
sys.exit(0 if s["state"] == "done" else 1)
