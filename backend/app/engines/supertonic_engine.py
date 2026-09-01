"""Supertonic 3 엔진 — 한국어 포함 31개 언어, 99M ONNX, CPU 실행.

2026-09-01 사용자 승인으로 추가한 세 번째 엔진. VibeVoice(영·중)가 못 하는
한국어를 맡는다. 실측: 한국어 8.85초를 CPU 2.53초에 합성(RTF 0.29),
onnxruntime 만 쓰므로 torch/transformers 핀과 충돌이 없고 VRAM 도 안 쓴다.

세그먼트 단위로 합성해 무음을 넣어 잇는다(Dia2 와 같은 구조) — 타임스탬프가
정확하고, 화자마다 다른 보이스 스타일(F1~F5 · M1~M5)을 줄 수 있다.
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

import numpy as np

from ..config import SUPERTONIC_MODEL
from ..schemas import Script, SegmentTiming
from .base import CancelFn, Engine, EngineError, ProgressFn, RenderResult, estimate_seconds

log = logging.getLogger(__name__)

SAMPLE_RATE = 44100
STYLE_IDS = ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]
VOICE_PREFIX = "st-"  # VibeVoice wav 프리셋과 id 충돌을 피한다


def voice_catalog() -> list[dict]:
    """/voices 에 실을 Supertonic 보이스 목록."""
    if not (SUPERTONIC_MODEL / "voice_styles").exists():
        return []
    out = []
    for sid in STYLE_IDS:
        gender = "여성" if sid.startswith("F") else "남성"
        out.append({
            "id": f"{VOICE_PREFIX}{sid}",
            "label": f"Supertonic {sid} · {gender}",
            "language": "한국어·다국어",
            "gender": gender,
            "engine": "supertonic",
            "has_bgm": False,
            "path": str(SUPERTONIC_MODEL / "voice_styles" / f"{sid}.json"),
        })
    return out


class SupertonicEngine(Engine):
    name = "supertonic"

    def __init__(self, *, lang: str = "ko", speed: float = 1.05, steps: int = 8,
                 gap_speaker_ms: int = 500, gap_paragraph_ms: int = 800) -> None:
        self._tts = None
        self._styles: dict[str, object] = {}
        self._lock = threading.Lock()
        self.lang = lang
        self.speed = speed
        self.steps = steps
        self.gap_speaker_ms = gap_speaker_ms
        self.gap_paragraph_ms = gap_paragraph_ms

    @property
    def loaded(self) -> bool:
        return self._tts is not None

    def load(self) -> None:
        with self._lock:
            if self._tts is not None:
                return
            if not (SUPERTONIC_MODEL / "onnx").exists():
                raise EngineError(
                    "model_missing",
                    "Supertonic 모델이 없습니다. 설정에서 내려받기를 시작해주세요.",
                )
            from supertonic import TTS

            # CPU 로 돌린다. 99M 이라 실시간보다 빠르고 GPU 엔진과 경합하지 않는다.
            self._tts = TTS(model="supertonic-3", model_dir=str(SUPERTONIC_MODEL),
                            auto_download=False)

    def unload(self) -> None:
        with self._lock:
            self._tts = None
            self._styles = {}

    def _style(self, voice_id: str | None):  # noqa: ANN202
        assert self._tts is not None
        sid = (voice_id or "").removeprefix(VOICE_PREFIX)
        if sid not in STYLE_IDS:
            sid = "F1"
        if sid not in self._styles:
            self._styles[sid] = self._tts.get_voice_style(sid)
        return self._styles[sid]

    def render(
        self,
        script: Script,
        voice_map: dict[str, str],
        *,
        on_progress: ProgressFn,
        should_cancel: CancelFn,
        seed: int | None = None,  # ONNX 경로라 시드가 필요 없다
        on_audio=None,  # noqa: ANN001
    ) -> RenderResult:
        self.load()
        assert self._tts is not None

        expected = estimate_seconds(script)
        chunks: list[np.ndarray] = []
        gaps: list[int] = []
        done_s = 0.0

        for i, seg in enumerate(script.segments):
            if should_cancel():
                raise EngineError("cancelled", "렌더를 취소했습니다.")
            text = re.sub(r"\s+", " ", seg.text).strip()
            style = self._style(voice_map.get(seg.speaker))
            try:
                wav, _ = self._tts.synthesize(
                    text, style, total_steps=self.steps, speed=self.speed,
                    lang=self.lang or None,
                )
            except Exception as exc:  # noqa: BLE001
                raise EngineError(
                    "synth_failed",
                    f"{i + 1}번째 구간 합성에 실패했습니다: {str(exc)[:120]}",
                ) from exc
            x = np.asarray(wav, dtype=np.float32).reshape(-1)
            chunks.append(x)
            done_s += len(x) / SAMPLE_RATE
            on_progress(done_s, max(expected, done_s),
                        f"{i + 1}/{len(script.segments)}번째 구간")
            if on_audio is not None:
                on_audio(x, SAMPLE_RATE)
            if i < len(script.segments) - 1:
                same = script.segments[i + 1].speaker == seg.speaker
                gap = self.gap_paragraph_ms if same else self.gap_speaker_ms
                gaps.append(gap)
                if on_audio is not None:
                    on_audio(np.zeros(int(SAMPLE_RATE * gap / 1000), dtype=np.float32),
                             SAMPLE_RATE)

        parts: list[np.ndarray] = []
        timings: list[SegmentTiming] = []
        cursor = 0
        for i, (seg, x) in enumerate(zip(script.segments, chunks)):
            start = cursor / SAMPLE_RATE
            parts.append(x)
            cursor += len(x)
            timings.append(SegmentTiming(
                index=i, speaker=seg.speaker, text=seg.text,
                start=round(start, 3), end=round(cursor / SAMPLE_RATE, 3),
                translation=seg.translation,
            ))
            if i < len(chunks) - 1:
                n = int(SAMPLE_RATE * gaps[i] / 1000)
                parts.append(np.zeros(n, dtype=np.float32))
                cursor += n

        audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        return RenderResult(audio=audio, sample_rate=SAMPLE_RATE, timings=timings,
                            timings_estimated=False, notes=[])
