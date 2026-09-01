"""엔진 공통 인터페이스."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np

from ..schemas import Script, SegmentTiming

# (완료된 초, 전체 예상 초, 사람이 읽을 메시지)
ProgressFn = Callable[[float, float, str], None]
CancelFn = Callable[[], bool]
# 합성되는 대로 PCM 을 받아 렌더 중 미리 듣기에 쓴다.
# (chunk, sample_rate) — chunk 가 None 이면 "처음부터 다시" (재시드 재시도 등)
AudioFn = Callable[["np.ndarray | None", int], None]


@dataclass
class RenderResult:
    audio: np.ndarray
    sample_rate: int
    timings: list[SegmentTiming]
    # 세그먼트 경계를 정확히 못 뽑아 비례 배분으로 추정했는지
    timings_estimated: bool = False
    notes: list[str] = field(default_factory=list)


class EngineError(RuntimeError):
    """엔진 실패. code 는 UI 가 화면을 고르는 데 쓴다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Engine(Protocol):
    name: str

    @property
    def loaded(self) -> bool: ...

    def load(self) -> None: ...

    def unload(self) -> None: ...

    def render(
        self,
        script: Script,
        voice_map: dict[str, str],
        *,
        on_progress: ProgressFn,
        should_cancel: CancelFn,
        seed: int | None = None,
        on_audio: "AudioFn | None" = None,
    ) -> RenderResult: ...


def estimate_seconds(script: Script) -> float:
    """대본 길이에서 오디오 길이를 추정한다.

    측정치: VibeVoice 가 130 단어를 51.5초로 읽었다 -> 약 2.5 단어/초.
    ETA 표시용이므로 정확할 필요는 없고, 0 이 되지 않기만 하면 된다.
    """
    words = sum(len(s.text.split()) for s in script.segments)
    return max(1.0, words / 2.5)
