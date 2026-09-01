"""엔드투엔드 검증: 같은 주제로 Narration 과 3인 Conversation 을 렌더한다.

확인할 것 (지침 검증 항목)
  - mp3 와 타임스탬프 json 이 나오는가
  - 세그먼트 경계가 실제 발화와 맞는가
  - /jobs 진행률이 도는가
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7861"
TOPIC = "고르는 법: 커피 원두"

NARRATION = {
    "title": "How to choose coffee beans",
    "format": "Narration",
    "segments": [
        {"speaker": "NARRATOR",
         "text": "Choosing coffee beans is mostly a question of how recently they were roasted.",
         "note": "calm, unhurried"},
        {"speaker": "NARRATOR",
         "text": "Look for a roast date on the bag, not a best before date. Anything within three weeks of roasting will taste alive.",
         "note": None},
        {"speaker": "NARRATOR",
         "text": "After that, decide how dark you want it, and buy whole beans if you can grind them yourself.",
         "note": None},
    ],
}

CONVERSATION = {
    "title": "How to choose coffee beans",
    "format": "Conversation",
    "segments": [
        {"speaker": "A", "text": "Okay, I need help. There are forty bags on this shelf and they all look the same.",
         "note": "a little overwhelmed"},
        {"speaker": "B", "text": "Start with the roast date. If it is not printed on the bag, put it back.", "note": None},
        {"speaker": "C", "text": "That is the whole trick, honestly. Freshness beats origin almost every time.", "note": None},
        {"speaker": "A", "text": "So the fancy single origin one from six months ago is worse than a cheap bag from last week?", "note": None},
        {"speaker": "B", "text": "Considerably worse. It will taste flat and a bit like cardboard.", "note": None},
        {"speaker": "C", "text": "Buy whole beans too. Ground coffee goes stale in about fifteen minutes.", "note": "matter of fact"},
        {"speaker": "A", "text": "Fifteen minutes. Right. I am going to pretend I did not hear that.", "note": None},
    ],
}


def render(payload: dict, engine: str = "vibevoice") -> dict:
    body = {"script": payload, "engine": engine, "seed": 1234}
    r = requests.post(f"{BASE}/render", json=body, timeout=30)
    r.raise_for_status()
    job = r.json()
    jid = job["id"]
    print(f"\n>>> {payload['format']}  job={jid}  세그먼트 {len(payload['segments'])}개")

    last = ""
    while True:
        s = requests.get(f"{BASE}/jobs/{jid}", timeout=30).json()
        line = (f"    {s['state']:<9} {s['progress'] * 100:5.1f}%  "
                f"경과 {s['elapsed']:6.1f}s  "
                f"남은 {('%.0fs' % s['eta']) if s.get('eta') else '  -':>5}  {s['message']}")
        if line != last:
            print(line, flush=True)
            last = line
        if s["state"] in ("done", "error", "cancelled"):
            return s
        time.sleep(1.5)


def show(result: dict) -> bool:
    if result["state"] != "done":
        print(f"    실패: [{result.get('error_code')}] {result.get('error')}")
        return False
    print(f"    mp3  : {result['audio_path']}")
    print(f"    대본 : {result['script_path']}")
    print(f"    타임 : {result['timing_path']}")
    print(f"    길이 : {result['duration']}s")
    for p in (result["audio_path"], result["script_path"], result["timing_path"]):
        if not Path(p).exists():
            print(f"    !! 파일이 없습니다: {p}")
            return False
    tj = json.loads(Path(result["timing_path"]).read_text("utf-8"))
    print(f"    경계 추정 사용: {tj['timings_estimated']}")
    print("    구간:")
    for s in tj["segments"]:
        print(f"      {s['index']:2d} {s['speaker']:<8} {s['start']:7.3f} - {s['end']:7.3f}  "
              f"{s['text'][:52]}")
    # 경계 연속성 검사
    prev = 0.0
    for s in tj["segments"]:
        if abs(s["start"] - prev) > 0.001:
            print(f"    !! 구간 {s['index']} 시작이 이전 끝과 어긋납니다")
            return False
        if s["end"] < s["start"]:
            print(f"    !! 구간 {s['index']} 끝이 시작보다 앞섭니다")
            return False
        prev = s["end"]
    if abs(prev - result["duration"]) > 0.05:
        print(f"    !! 마지막 구간 끝 {prev} 이 전체 길이 {result['duration']} 와 다릅니다")
        return False
    print("    구간 연속성 OK")
    return True


if __name__ == "__main__":
    h = requests.get(f"{BASE}/health", timeout=10).json()
    print(f"백엔드 {h['version']}  {h['device']}  VRAM {h['vram_used_gb']}/{h['vram_total_gb']} GB")

    ok = True
    for payload in (NARRATION, CONVERSATION):
        ok &= show(render(payload))

    h2 = requests.get(f"{BASE}/health", timeout=10).json()
    print(f"\n렌더 후 VRAM {h2['vram_used_gb']}/{h2['vram_total_gb']} GB  "
          f"상주 엔진 {h2['engine_loaded']}")
    print("\n" + ("전체 통과" if ok else "실패 항목 있음"))
    sys.exit(0 if ok else 1)
