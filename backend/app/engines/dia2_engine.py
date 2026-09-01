"""Dia2-2B 엔진 (보조).

지침이 요구하는 "세그먼트 캐시로 수정 줄만 재합성"을 만족시키려면 캐시 단위가
줄이어야 한다. 따라서 세그먼트를 하나씩 합성하고 무음을 넣어 이어붙인다.

  - 화자 전환 0.5초, 같은 화자 연속(문단 전환) 0.8초 무음
  - 줄 단위이므로 1회 2분 상한(max_context_steps 1500 @ 12.5Hz)에 걸리지 않는다
  - 내용 해시로 캐시하므로 한 줄만 고치면 그 줄만 다시 합성된다

트레이드오프: 줄 단위 합성은 턴을 가로지르는 억양 연결을 잃는다. 대신 정확한
세그먼트 타임스탬프와 부분 재합성을 얻는다. 지침의 검증 항목이 후자를 요구한다.

Windows 주의: CUDA 그래프를 끄면 RTF 가 0.76 -> 4.87 로 무너진다(WDDM 커널 런치
오버헤드). 기본으로 켠 채 둔다.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from ..audio import inspect_array
from ..config import BACKEND_ROOT, DIA2_MODEL, MIMI_MODEL
from ..schemas import Script, SegmentTiming
from .base import CancelFn, Engine, EngineError, ProgressFn, RenderResult, estimate_seconds

log = logging.getLogger(__name__)

SAMPLE_RATE = 24000
CACHE_DIR = BACKEND_ROOT / "cache" / "dia2"


def _cache_key(text: str, note: str | None, slot: str, temperature: float,
               top_k: int, cfg_scale: float) -> str:
    # v2: 노트를 그대로 읽던 시절의 캐시를 무효화한다. 키 형식이 바뀌면
    # 이전 항목은 자연히 미스가 나서 새로 합성된다.
    raw = f"v2|{slot}|{text}|{note or ''}|{temperature}|{top_k}|{cfg_scale}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# Dia 계열이 소리로 해석하는 비언어 태그. 이 밖의 노트("cheerful, relaxed" 같은
# 서술)는 태그가 아니라 텍스트로 읽혀 버리므로 프롬프트에 넣지 않는다(실사용 확인).
NONVERBAL_TAGS = {
    "laughs", "laugh", "chuckles", "chuckle", "giggles",
    "sighs", "sigh", "gasps", "gasp",
    "coughs", "cough", "clears throat",
    "sniffs", "groans", "hums", "humming", "whistles",
    "inhales", "exhales", "screams", "mumbles",
}


def build_line(text: str, note: str | None, slot: str) -> str:
    """한 줄을 Dia2 대본 형식으로.

    note 는 알려진 비언어 태그일 때만 태그로 붙인다. 서술형 노트를 붙이면
    모델이 그 단어들을 그대로 발음한다.
    """
    body = re.sub(r"\s+", " ", text).strip().replace("’", "'")
    if note:
        tag = re.sub(r"\s+", " ", note).strip().strip("()").lower()
        if tag in NONVERBAL_TAGS:
            body = f"({tag}) {body}"
    return f"[{slot}] {body}"


class Dia2Engine(Engine):
    name = "dia2"

    def __init__(
        self,
        *,
        cuda_graph: bool = True,
        temperature: float = 0.8,
        top_k: int = 50,
        cfg_scale: float = 1.0,
        max_retries: int = 2,
        gap_speaker_ms: int = 500,
        gap_paragraph_ms: int = 800,
    ) -> None:
        self._dia = None
        self._lock = threading.Lock()
        self.cuda_graph = cuda_graph
        self.temperature = temperature
        self.top_k = top_k
        self.cfg_scale = cfg_scale
        self.max_retries = max_retries
        self.gap_speaker_ms = gap_speaker_ms
        self.gap_paragraph_ms = gap_paragraph_ms

    @property
    def loaded(self) -> bool:
        return self._dia is not None

    def load(self) -> None:
        with self._lock:
            if self._dia is not None:
                return
            if not (DIA2_MODEL / "model.safetensors").exists():
                raise EngineError(
                    "model_missing",
                    "Dia2 가중치가 없습니다. 설정에서 내려받기를 시작해주세요.",
                )
            if not (MIMI_MODEL / "model.safetensors").exists():
                raise EngineError(
                    "model_missing",
                    "Mimi 코덱이 없습니다. 설정에서 내려받기를 시작해주세요.",
                )
            from dia2.engine import Dia2

            try:
                self._dia = Dia2.from_local(
                    config_path=str(DIA2_MODEL / "config.json"),
                    weights_path=str(DIA2_MODEL / "model.safetensors"),
                    tokenizer_id=str(DIA2_MODEL),
                    mimi_id=str(MIMI_MODEL),
                    device="cuda",
                    dtype="bfloat16",
                )
            except torch.cuda.OutOfMemoryError as exc:
                raise EngineError(
                    "vram",
                    "GPU 메모리가 부족해 Dia2를 올리지 못했습니다. 다른 GPU 프로그램을 닫아주세요.",
                ) from exc

    def unload(self) -> None:
        with self._lock:
            self._dia = None
            torch.cuda.empty_cache()

    # ------------------------------------------------------------------

    def _synth_line(self, line: str, seed: int) -> np.ndarray:
        """한 줄 합성. 발산 출력이면 시드를 바꿔 다시 시도한다."""
        from dia2.generation import build_generation_config, validate_generation_params

        assert self._dia is not None
        t, k, c = validate_generation_params(
            temperature=self.temperature, top_k=self.top_k, cfg_scale=self.cfg_scale
        )
        cfg = build_generation_config(temperature=t, top_k=k, cfg_scale=c)

        last_qc = None
        for attempt in range(self.max_retries + 1):
            s = seed + attempt * 7919
            torch.manual_seed(s)
            torch.cuda.manual_seed_all(s)
            # mkstemp 는 열린 fd 를 준다. Windows 는 열린 파일을 지우지 못하므로
            # 바로 닫고 경로만 쓴다.
            fd, tmp_name = tempfile.mkstemp(suffix=".wav", dir=str(CACHE_DIR))
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                self._dia.generate(
                    line, config=cfg, output_wav=str(tmp), verbose=False,
                    use_cuda_graph=self.cuda_graph,
                )
                x, sr = sf.read(str(tmp), dtype="float32", always_2d=False)
            finally:
                tmp.unlink(missing_ok=True)

            x = np.asarray(x, dtype=np.float32).reshape(-1)
            qc = inspect_array(x, sr)
            last_qc = qc
            if not qc.degenerate:
                return x
            log.warning(
                "dia2 출력 발산 (시도 %d): peak=%.3f rms=%.1fdBFS clipped=%d",
                attempt + 1, qc.peak, qc.rms_dbfs, qc.clipped_samples,
            )

        raise EngineError(
            "degenerate_output",
            "Dia2가 이 줄에서 계속 왜곡된 소리를 냅니다. 문장을 짧게 나누거나 "
            "VibeVoice로 바꿔보세요.",
        )

    def render(
        self,
        script: Script,
        voice_map: dict[str, str],
        *,
        on_progress: ProgressFn,
        should_cancel: CancelFn,
        seed: int | None = None,
        on_audio=None,  # noqa: ANN001
        references: dict[str, str] | None = None,
    ) -> RenderResult:
        order = script.speakers()
        if len(order) > 2:
            raise EngineError(
                "too_many_speakers",
                f"화자가 {len(order)}명입니다. Dia2는 2명까지입니다. VibeVoice로 바꿔주세요.",
            )
        slot_of = {sp: ("S1" if i == 0 else "S2") for i, sp in enumerate(order)}

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.load()

        if references:
            # 레퍼런스 클로닝은 프리픽스 전사 비용 때문에 줄 단위가 아니라
            # 턴 묶음(2분 상한 아래) 단위로 합성한다. 캐시 없음.
            return self._render_cloned(
                script, slot_of, references,
                on_progress=on_progress, should_cancel=should_cancel,
                seed=seed, on_audio=on_audio,
            )

        base_seed = seed if seed is not None else 1234
        expected = estimate_seconds(script)
        chunks: list[np.ndarray] = []
        gaps: list[int] = []
        notes: list[str] = []
        cached_count = 0
        done_s = 0.0

        for i, seg in enumerate(script.segments):
            if should_cancel():
                raise EngineError("cancelled", "렌더를 취소했습니다.")

            slot = slot_of[seg.speaker]
            key = _cache_key(seg.text, seg.note, slot,
                             self.temperature, self.top_k, self.cfg_scale)
            cached = CACHE_DIR / f"{key}.wav"

            if cached.exists():
                x, _ = sf.read(str(cached), dtype="float32", always_2d=False)
                x = np.asarray(x, dtype=np.float32).reshape(-1)
                cached_count += 1
            else:
                line = build_line(seg.text, seg.note, slot)
                x = self._synth_line(line, base_seed + i)
                sf.write(str(cached), x, SAMPLE_RATE, subtype="PCM_16")

            chunks.append(x)
            done_s += len(x) / SAMPLE_RATE
            on_progress(
                done_s, max(expected, done_s),
                f"{i + 1}/{len(script.segments)}번째 구간",
            )
            if on_audio is not None:
                on_audio(x, SAMPLE_RATE)

            if i < len(script.segments) - 1:
                same_speaker = script.segments[i + 1].speaker == seg.speaker
                gap = self.gap_paragraph_ms if same_speaker else self.gap_speaker_ms
                gaps.append(gap)
                if on_audio is not None:
                    on_audio(np.zeros(int(SAMPLE_RATE * gap / 1000), dtype=np.float32),
                             SAMPLE_RATE)

        if cached_count:
            notes.append(f"{cached_count}개 구간을 캐시에서 재사용했습니다.")

        # 무음을 넣어 이어붙이면서 경계를 기록한다
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
                if n > 0:
                    parts.append(np.zeros(n, dtype=np.float32))
                    cursor += n

        audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        return RenderResult(
            audio=audio, sample_rate=SAMPLE_RATE, timings=timings,
            timings_estimated=False, notes=notes,
        )

    # ------------------------------------------------------------------
    # 레퍼런스 클로닝

    _whisper_patched = False

    @classmethod
    def _patch_whisper_cache(cls) -> None:
        """dia2 는 프리픽스를 전사할 때마다 whisper 를 새로 로드한다.

        vendored 코드를 고치지 않고, whisper_timestamped.load_model 을
        캐시 래퍼로 감싸 로드를 1회로 줄인다 (large-v3 로드는 십수 초).
        """
        if cls._whisper_patched:
            return
        import functools

        import whisper_timestamped as wts

        original = wts.load_model

        @functools.lru_cache(maxsize=2)
        def cached(name: str, device: str = "cpu", *args, **kwargs):  # noqa: ANN002, ANN003
            return original(name, device, *args, **kwargs)

        wts.load_model = cached  # type: ignore[assignment]
        cls._whisper_patched = True

    def _prep_reference(self, path: str) -> str:
        """레퍼런스 wav 를 24kHz 모노로 맞춰 임시 파일로 만든다.

        dia2 의 sphn 폴백 리샘플러가 선형 보간이라 품질이 낮으므로
        (SETUP.md 5-1) 우리가 미리 soxr 로 리샘플해서 넘긴다.
        """
        import librosa

        y, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
        if len(y) < SAMPLE_RATE:
            raise EngineError(
                "bad_reference",
                "레퍼런스 오디오가 1초보다 짧습니다. 5~30초짜리 wav를 써주세요.",
            )
        # 30초가 넘으면 앞 30초만 (프리픽스가 길수록 전사·워밍업이 느려진다)
        y = y[: SAMPLE_RATE * 30]
        fd, tmp_name = tempfile.mkstemp(suffix=".wav", dir=str(CACHE_DIR))
        os.close(fd)
        sf.write(tmp_name, y, SAMPLE_RATE, subtype="PCM_16")
        return tmp_name

    def _render_cloned(
        self,
        script: Script,
        slot_of: dict[str, str],
        references: dict[str, str],
        *,
        on_progress: ProgressFn,
        should_cancel: CancelFn,
        seed: int | None,
        on_audio=None,  # noqa: ANN001
    ) -> RenderResult:
        from dia2.generation import build_generation_config, validate_generation_params

        from ..timing import segment_bounds, text_weight
        from .base import estimate_seconds

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._patch_whisper_cache()

        order = list(slot_of.keys())
        prefix1 = references.get(order[0])
        prefix2 = references.get(order[1]) if len(order) > 1 else None
        if not prefix1 and not prefix2:
            raise EngineError("bad_reference", "레퍼런스 오디오가 지정되지 않았습니다.")
        p1 = self._prep_reference(prefix1) if prefix1 else None
        p2 = self._prep_reference(prefix2) if prefix2 else None

        # 턴을 2분 상한(여유 있게 90초 추정) 아래 묶음으로 나눈다
        chunks: list[list[int]] = [[]]
        acc_words = 0
        for i, seg in enumerate(script.segments):
            w = len(seg.text.split())
            if chunks[-1] and (acc_words + w) / 2.5 > 90:
                chunks.append([])
                acc_words = 0
            chunks[-1].append(i)
            acc_words += w

        t, k, c = validate_generation_params(
            temperature=self.temperature, top_k=self.top_k, cfg_scale=self.cfg_scale
        )
        cfg = build_generation_config(temperature=t, top_k=k, cfg_scale=c)
        base_seed = seed if seed is not None else 1234
        expected = estimate_seconds(script)

        pieces: list[np.ndarray] = []      # 청크 오디오
        chunk_bounds: list[list[float]] = []  # 청크 내부 세그먼트 끝(초)
        done_s = 0.0
        notes = [f"레퍼런스 클로닝: {len(chunks)}개 묶음으로 합성"]

        try:
            for ci, idxs in enumerate(chunks):
                if should_cancel():
                    raise EngineError("cancelled", "렌더를 취소했습니다.")
                text = " ".join(
                    build_line(script.segments[i].text, script.segments[i].note,
                               slot_of[script.segments[i].speaker])
                    for i in idxs
                )

                last_qc = None
                x = None
                for attempt in range(self.max_retries + 1):
                    s = base_seed + ci * 101 + attempt * 7919
                    torch.manual_seed(s)
                    torch.cuda.manual_seed_all(s)
                    fd, tmp_name = tempfile.mkstemp(suffix=".wav", dir=str(CACHE_DIR))
                    os.close(fd)
                    tmp = Path(tmp_name)
                    try:
                        assert self._dia is not None
                        self._dia.generate(
                            text, config=cfg, output_wav=str(tmp), verbose=False,
                            use_cuda_graph=self.cuda_graph,
                            prefix_speaker_1=p1, prefix_speaker_2=p2,
                        )
                        cand, _ = sf.read(str(tmp), dtype="float32", always_2d=False)
                    finally:
                        tmp.unlink(missing_ok=True)
                    cand = np.asarray(cand, dtype=np.float32).reshape(-1)
                    qc = inspect_array(cand, SAMPLE_RATE)
                    last_qc = qc
                    if not qc.degenerate:
                        x = cand
                        break
                    log.warning("클로닝 묶음 %d 발산 (시도 %d)", ci, attempt + 1)
                if x is None:
                    raise EngineError(
                        "degenerate_output",
                        f"{ci + 1}번째 묶음이 계속 왜곡됩니다. 레퍼런스를 더 깨끗한 "
                        f"녹음으로 바꾸거나 대본을 줄여보세요.",
                    )

                pieces.append(x)
                dur = len(x) / SAMPLE_RATE
                weights = [text_weight(script.segments[i].text) for i in idxs]
                bounds, _q = segment_bounds(weights, dur, [], x)
                chunk_bounds.append(bounds)
                done_s += dur
                on_progress(done_s, max(expected, done_s),
                            f"{ci + 1}/{len(chunks)}번째 묶음")
                if on_audio is not None:
                    on_audio(x, SAMPLE_RATE)
                    if ci < len(chunks) - 1:
                        on_audio(np.zeros(int(SAMPLE_RATE * self.gap_paragraph_ms / 1000),
                                          dtype=np.float32), SAMPLE_RATE)
        finally:
            for pth in (p1, p2):
                if pth:
                    Path(pth).unlink(missing_ok=True)

        # 이어붙이기 + 타임스탬프 (묶음 사이 문단 간격)
        parts: list[np.ndarray] = []
        timings: list[SegmentTiming] = []
        cursor = 0
        for ci, (idxs, x) in enumerate(zip(chunks, pieces)):
            base = cursor / SAMPLE_RATE
            parts.append(x)
            cursor += len(x)
            prev = 0.0
            for j, i in enumerate(idxs):
                seg = script.segments[i]
                end = chunk_bounds[ci][j]
                timings.append(SegmentTiming(
                    index=i, speaker=seg.speaker, text=seg.text,
                    start=round(base + prev, 3), end=round(base + end, 3),
                    translation=seg.translation,
                ))
                prev = end
            if ci < len(pieces) - 1:
                n = int(SAMPLE_RATE * self.gap_paragraph_ms / 1000)
                parts.append(np.zeros(n, dtype=np.float32))
                cursor += n

        audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        notes.append("묶음 내부 구간 경계는 무음 정렬 추정입니다.")
        return RenderResult(audio=audio, sample_rate=SAMPLE_RATE, timings=timings,
                            timings_estimated=True, notes=notes)

    @staticmethod
    def clear_cache() -> int:
        if not CACHE_DIR.exists():
            return 0
        n = len(list(CACHE_DIR.glob("*.wav")))
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        return n
