"""Dia2 세그먼트 캐시 검증.

지침 검증 항목: "Dia2 경로에서 한 줄만 수정 후 재렌더 시 그 줄만 다시 합성되는지"

1회차: 전부 새로 합성
2회차: 대본 그대로  -> 전부 캐시 적중, 훨씬 빨라야 한다
3회차: 3번 줄만 수정 -> 그 줄만 새로 합성, 나머지는 캐시
"""
from __future__ import annotations

import copy
import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7861"

SCRIPT = {
    "title": "Dia2 cache check",
    "format": "Conversation",
    "segments": [
        {"speaker": "A", "text": "So did you end up fixing the render pipeline?", "note": None},
        {"speaker": "B", "text": "Mostly. The caching part was the fiddly bit.", "note": None},
        {"speaker": "A", "text": "What was fiddly about it exactly?", "note": None},
        {"speaker": "B", "text": "Working out what counts as one unit of work.", "note": None},
    ],
}


def run(script: dict, label: str) -> dict:
    t0 = time.time()
    r = requests.post(f"{BASE}/render",
                      json={"script": script, "engine": "dia2", "seed": 1234}, timeout=30)
    r.raise_for_status()
    jid = r.json()["id"]
    while True:
        s = requests.get(f"{BASE}/jobs/{jid}", timeout=30).json()
        if s["state"] in ("done", "error", "cancelled"):
            break
        time.sleep(1.0)
    wall = time.time() - t0
    print(f"\n--- {label} ---")
    if s["state"] != "done":
        print(f"  실패 [{s.get('error_code')}] {s.get('error')}")
        return s
    print(f"  벽시계 {wall:6.1f}s   렌더 {s['elapsed']:6.1f}s   길이 {s['duration']}s")
    print(f"  메시지: {s['message']}")
    for t in s["timings"]:
        print(f"    {t['index']} {t['speaker']} {t['start']:6.3f}-{t['end']:6.3f}  {t['text'][:46]}")
    return s


if __name__ == "__main__":
    requests.post(f"{BASE}/cache/clear", timeout=30)
    print("캐시를 비우고 시작합니다.")

    first = run(SCRIPT, "1회차 · 캐시 없음")
    second = run(SCRIPT, "2회차 · 대본 동일")

    edited = copy.deepcopy(SCRIPT)
    edited["segments"][2]["text"] = "Which part gave you the most trouble?"
    third = run(edited, "3회차 · 3번째 줄만 수정")

    print("\n=== 판정 ===")
    ok = True
    for s, label in ((first, "1회차"), (second, "2회차"), (third, "3회차")):
        if s["state"] != "done":
            print(f"  {label} 실패")
            ok = False
    if ok:
        t1, t2, t3 = first["elapsed"], second["elapsed"], third["elapsed"]
        print(f"  1회차 {t1:.1f}s / 2회차 {t2:.1f}s / 3회차 {t3:.1f}s")
        if t2 < t1 * 0.35:
            print(f"  2회차가 1회차의 {t2/t1*100:.0f}% -> 캐시 적중 확인")
        else:
            print(f"  !! 2회차가 충분히 빠르지 않습니다 ({t2/t1*100:.0f}%)")
            ok = False
        # 한 줄만 다시 합성했다면 3회차는 1회차의 대략 1/4 근처여야 한다
        if t3 < t1 * 0.6:
            print(f"  3회차가 1회차의 {t3/t1*100:.0f}% -> 수정한 줄만 재합성 확인")
        else:
            print(f"  !! 3회차가 너무 오래 걸렸습니다 ({t3/t1*100:.0f}%)")
            ok = False
        # 수정하지 않은 줄들의 길이가 그대로인지
        for i in (0, 1, 3):
            a = first["timings"][i]
            b = third["timings"][i]
            if abs((a["end"] - a["start"]) - (b["end"] - b["start"])) > 0.001:
                print(f"  !! 구간 {i} 길이가 바뀌었습니다 (캐시가 안 쓰였을 수 있음)")
                ok = False
        else:
            print("  수정하지 않은 구간의 길이가 1회차와 동일 -> 캐시 재사용 확인")
    print("\n" + ("통과" if ok else "실패"))
    sys.exit(0 if ok else 1)
