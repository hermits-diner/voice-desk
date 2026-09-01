"""세그먼트 타임스탬프 산출.

VibeVoice 는 대본 전체를 한 번에 렌더하므로 턴 경계를 따로 알아내야 한다.
측정으로 확인한 사실 세 가지를 조합한다.

  1. 확산 토큰 1개 == 정확히 3200 샘플. 예외 없음.
  2. 모델이 찍는 speech_end 토큰의 위치는 정확한 발화 경계다.
     다만 개수가 우리 턴 수와 일치하지 않는다. 화자가 매 턴 바뀌면 대체로
     맞고(2인 교대 4턴 -> END 4개), 같은 화자가 이어지거나 화자가 3명 이상이면
     모델이 여러 턴을 한 덩어리로 묶는다(3인 교대 6턴 -> END 1개).
  3. 턴 경계에는 거의 항상 짧은 무음이 있다.

전략
  - 단어 수와 문장부호로 각 턴의 예상 길이를 잡고 전체 길이에 맞춰 늘린다.
  - 모델이 준 END 를 앵커로 삼아 가장 가까운 예상 경계를 그 값으로 고정한다.
  - 앵커가 없는 경계는 예상 위치 주변에서 가장 조용한 지점으로 스냅한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 24000
SAMPLES_PER_FRAME = 3200

# 문장부호가 만드는 추가 정지 (단어 환산)
_PAUSE_WEIGHT = {".": 1.2, "?": 1.4, "!": 1.4, ",": 0.4, ";": 0.7, ":": 0.7, "—": 0.6}


@dataclass
class TimingQuality:
    anchored: int          # 모델 END 로 정확히 고정한 경계 수
    snapped: int           # 무음으로 스냅한 경계 수
    estimated: int         # 순수 비례 추정으로 남은 경계 수
    total: int

    @property
    def exact(self) -> bool:
        return self.anchored == self.total

    def describe(self) -> str:
        if self.exact:
            return "세그먼트 경계를 모델 출력에서 그대로 읽었습니다."
        parts = []
        if self.anchored:
            parts.append(f"{self.anchored}개 정확")
        if self.snapped:
            parts.append(f"{self.snapped}개 무음 정렬")
        if self.estimated:
            parts.append(f"{self.estimated}개 추정")
        return "세그먼트 경계: " + ", ".join(parts) + "."


def text_weight(text: str) -> float:
    """읽는 데 걸리는 상대 시간. 단어 수 + 문장부호 정지."""
    w = float(len(text.split()))
    for ch, extra in _PAUSE_WEIGHT.items():
        w += text.count(ch) * extra
    return max(w, 0.5)


def end_anchors(generated: list[int], speech_end_id: int, speech_diffusion_id: int) -> list[float]:
    """생성 토큰 열에서 speech_end 가 찍힌 시각(초)."""
    out: list[float] = []
    acc = 0
    for t in generated:
        if t == speech_diffusion_id:
            acc += 1
        elif t == speech_end_id:
            out.append(acc * SAMPLES_PER_FRAME / SAMPLE_RATE)
    return out


def _quietest(audio: np.ndarray, center_s: float, window_s: float = 0.45) -> float | None:
    """center 주변 window 안에서 가장 조용한 20ms 지점을 찾는다."""
    hop = int(SAMPLE_RATE * 0.01)
    win = int(SAMPLE_RATE * 0.02)
    lo = max(0, int((center_s - window_s) * SAMPLE_RATE))
    hi = min(len(audio) - win, int((center_s + window_s) * SAMPLE_RATE))
    if hi <= lo:
        return None
    best, best_e = None, None
    for i in range(lo, hi, hop):
        e = float(np.abs(audio[i:i + win]).mean())
        if best_e is None or e < best_e:
            best_e, best = e, i
    if best is None:
        return None
    return (best + win / 2) / SAMPLE_RATE


def segment_bounds(
    weights: list[float],
    total_seconds: float,
    anchors: list[float],
    audio: np.ndarray | None = None,
) -> tuple[list[float], TimingQuality]:
    """각 세그먼트의 끝 시각을 돌려준다. 길이는 len(weights).

    anchors 는 모델이 준 정확한 경계다. 개수가 맞으면 그대로 쓰고,
    적으면 가까운 경계에 배정한 뒤 나머지를 채운다.
    """
    n = len(weights)
    if n == 0:
        return [], TimingQuality(0, 0, 0, 0)

    total_w = sum(weights)
    expected: list[float] = []
    run = 0.0
    for w in weights:
        run += total_seconds * w / total_w
        expected.append(run)
    expected[-1] = total_seconds

    # 마지막 앵커는 대본 끝이므로 경계 후보에서 뺀다
    inner = [a for a in anchors if 0.05 < a < total_seconds - 0.05]

    if len(anchors) == n:
        bounds = list(anchors)
        bounds[-1] = max(bounds[-1], total_seconds)
        return [round(b, 3) for b in bounds], TimingQuality(n, 0, 0, n)

    fixed: dict[int, float] = {n - 1: total_seconds}
    used: set[int] = set()
    # 앵커를 가장 가까운 예상 경계에 배정한다 (한 경계에 하나씩)
    for a in inner:
        cand = sorted(range(n - 1), key=lambda i: abs(expected[i] - a))
        for i in cand:
            if i not in used:
                used.add(i)
                fixed[i] = a
                break

    bounds: list[float] = []
    snapped = 0
    prev = 0.0
    for i in range(n):
        if i in fixed:
            b = fixed[i]
        else:
            b = expected[i]
            if audio is not None and audio.size:
                q = _quietest(audio, b)
                if q is not None and q > prev + 0.05:
                    b = q
                    snapped += 1
        b = max(b, prev + 0.05)
        b = min(b, total_seconds)
        bounds.append(b)
        prev = b
    bounds[-1] = total_seconds

    anchored = len(used) + 1  # 마지막 경계는 전체 길이로 항상 정확
    return (
        [round(b, 3) for b in bounds],
        TimingQuality(anchored, snapped, n - anchored - snapped, n),
    )
