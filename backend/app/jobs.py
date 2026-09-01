"""백그라운드 작업 관리 — 렌더는 요청을 붙잡지 않고 /jobs/{id} 로 진행률을 낸다.

GPU 작업은 한 번에 하나만 돌린다. 두 개가 겹치면 VRAM 이 터진다.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable

from .schemas import JobStatus, SegmentTiming

# GPU 를 쓰는 구간 전체를 감싸는 락. 큐잉은 이 락이 대신한다.
GPU_LOCK = threading.Lock()


class Job:
    def __init__(self, kind: str) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.state = "queued"
        self.progress = 0.0
        self.message = "대기 중"
        self.segment_index: int | None = None
        self.segment_total: int | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.eta: float | None = None
        self.audio_path: str | None = None
        self.script_path: str | None = None
        self.timing_path: str | None = None
        self.duration: float | None = None
        self.timings: list[SegmentTiming] | None = None
        self.error_code: str | None = None
        self.error: str | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        # 렌더 중 미리 듣기용 PCM 버퍼 (int16 mono). 6분 오디오라야 ~17MB.
        self._pcm = bytearray()
        self.pcm_sr: int | None = None

    # 취소 -----------------------------------------------------------
    def cancel(self) -> None:
        self._cancel.set()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # 진행률 ---------------------------------------------------------
    def set_state(self, state: str, message: str = "") -> None:
        with self._lock:
            self.state = state
            if message:
                self.message = message
            if state == "running" and self.started_at is None:
                self.started_at = time.time()
            if state in ("done", "error", "cancelled"):
                self.finished_at = time.time()

    def report(self, done_s: float, total_s: float, message: str) -> None:
        """엔진이 부르는 진행률 콜백. done_s / total_s 는 '오디오 초' 단위."""
        with self._lock:
            frac = 0.0 if total_s <= 0 else min(0.99, done_s / total_s)
            self.progress = frac
            self.message = message
            if self.started_at and frac > 0.02:
                elapsed = time.time() - self.started_at
                self.eta = max(0.0, elapsed / frac - elapsed)

    def set_segment(self, index: int, total: int) -> None:
        with self._lock:
            self.segment_index = index
            self.segment_total = total

    # 미리 듣기 PCM ---------------------------------------------------
    def push_pcm(self, chunk, sr: int) -> None:  # noqa: ANN001
        """엔진이 합성하는 대로 부르는 콜백. chunk=None 이면 처음부터 다시."""
        import numpy as np

        with self._lock:
            if chunk is None:
                self._pcm = bytearray()
                return
            self.pcm_sr = sr
            x = np.clip(np.asarray(chunk, dtype=np.float32).reshape(-1), -1.0, 1.0)
            self._pcm += (x * 32767.0).astype("<i2").tobytes()

    def read_pcm(self, from_byte: int) -> tuple[bytes, int, int | None]:
        """(데이터, 전체 바이트 수, 샘플레이트). from_byte 이후의 새 데이터만 준다."""
        with self._lock:
            total = len(self._pcm)
            start = min(max(0, from_byte), total)
            return bytes(self._pcm[start:total]), total, self.pcm_sr

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)

    def status(self) -> JobStatus:
        with self._lock:
            return JobStatus(
                id=self.id,
                state=self.state,  # type: ignore[arg-type]
                kind=self.kind,  # type: ignore[arg-type]
                progress=round(self.progress, 4),
                segment_index=self.segment_index,
                segment_total=self.segment_total,
                message=self.message,
                started_at=self.started_at,
                elapsed=self.elapsed,
                eta=round(self.eta, 1) if self.eta is not None else None,
                audio_path=self.audio_path,
                script_path=self.script_path,
                timing_path=self.timing_path,
                duration=self.duration,
                timings=self.timings,
                error_code=self.error_code,
                error=self.error,
            )


class JobRegistry:
    def __init__(self, keep: int = 50) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._keep = keep
        self._lock = threading.Lock()

    def create(self, kind: str) -> Job:
        job = Job(kind)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            while len(self._order) > self._keep:
                old = self._order.pop(0)
                j = self._jobs.get(old)
                if j and j.state in ("done", "error", "cancelled"):
                    self._jobs.pop(old, None)
                else:
                    self._order.insert(0, old)
                    break
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def recent(self, limit: int = 20) -> list[Job]:
        """최근 작업 목록 (큐 표시용). 새것부터."""
        with self._lock:
            ids = list(reversed(self._order[-limit:]))
        return [self._jobs[i] for i in ids if i in self._jobs]

    def run(self, job: Job, fn: Callable[[Job], None]) -> None:
        """작업을 백그라운드 스레드에서 돌린다."""
        def wrapper() -> None:
            from .engines.base import EngineError

            try:
                with GPU_LOCK:
                    if job.cancelled():
                        job.set_state("cancelled", "취소했습니다.")
                        return
                    job.set_state("running", "시작")
                    fn(job)
                if job.state not in ("error", "cancelled"):
                    job.progress = 1.0
                    job.set_state("done", "완료")
            except EngineError as exc:
                job.error_code = exc.code
                job.error = exc.message
                job.set_state("cancelled" if exc.code == "cancelled" else "error", exc.message)
            except Exception as exc:  # noqa: BLE001
                from .secrets_store import redact
                job.error_code = "internal"
                job.error = redact(f"{type(exc).__name__}: {exc}")[:400]
                job.set_state("error", job.error)

        threading.Thread(target=wrapper, name=f"job-{job.id}", daemon=True).start()
