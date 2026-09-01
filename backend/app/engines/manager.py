"""엔진 상주 · 교체 관리.

두 엔진을 동시에 올리면 12.7 GB 상주 + 피크가 겹칠 여지가 있어, 지침대로
선택된 하나만 올리고 전환 시 교체한다.
"""
from __future__ import annotations

import logging
import threading

from ..config import Settings
from .base import Engine, EngineError

# torch 와 엔진 모듈은 여기서 임포트하지 않는다. 둘 다 무거워서(이 PC 에서 20~30초)
# 서버 기동이 그만큼 늦어지고, 그 사이 /health 가 응답하지 않아 앱이 "백엔드 없음"
# 화면을 띄운다. 실제로 필요할 때 불러온다.

log = logging.getLogger(__name__)


# GPU 를 쓰는 엔진들. supertonic 은 CPU(onnx)라 여기 없고, GPU 엔진과
# 나란히 상주해도 VRAM 을 먹지 않으므로 교체 대상에서 뺀다.
GPU_ENGINES = {"vibevoice", "dia2"}


class EngineManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._current: Engine | None = None      # GPU 엔진 슬롯 (하나만)
        self._cpu: dict[str, Engine] = {}        # CPU 엔진들 (상주 무해)
        self._lock = threading.RLock()

    @property
    def loaded_name(self) -> str | None:
        return self._current.name if self._current and self._current.loaded else None

    def _build(self, name: str) -> Engine:
        s = self._settings
        if name == "vibevoice":
            from .vibevoice_engine import VibeVoiceEngine

            return VibeVoiceEngine(
                ddpm_steps=s.vv_ddpm_steps, cfg_scale=s.vv_cfg_scale,
                polish=s.vv_polish,
            )
        if name == "dia2":
            from .dia2_engine import Dia2Engine

            return Dia2Engine(
                cuda_graph=s.dia2_cuda_graph,
                temperature=s.dia2_temperature,
                top_k=s.dia2_top_k,
                cfg_scale=s.dia2_cfg_scale,
                max_retries=s.dia2_max_retries,
                gap_speaker_ms=s.gap_speaker_ms,
                gap_paragraph_ms=s.gap_paragraph_ms,
            )
        if name == "supertonic":
            from .supertonic_engine import SupertonicEngine

            return SupertonicEngine(
                lang=s.supertonic_lang,
                speed=s.supertonic_speed,
                steps=s.supertonic_steps,
                gap_speaker_ms=s.gap_speaker_ms,
                gap_paragraph_ms=s.gap_paragraph_ms,
            )
        raise EngineError("unknown_engine", f"모르는 엔진입니다: {name}")

    def get(self, name: str | None = None) -> Engine:
        """요청한 엔진을 준비해서 돌려준다.

        GPU 엔진은 하나만 상주하고 교체 시 내린다. CPU 엔진(supertonic)은
        VRAM 을 안 쓰므로 GPU 엔진을 건드리지 않고 나란히 둔다.
        """
        target = name or self._settings.engine
        with self._lock:
            if target not in GPU_ENGINES:
                if target not in self._cpu:
                    self._cpu[target] = self._build(target)
                self._cpu[target].load()
                return self._cpu[target]

            if self._current is not None and self._current.name != target:
                log.info("엔진 교체: %s -> %s", self._current.name, target)
                self._current.unload()
                _empty_cache()
                self._current = None
            if self._current is None:
                self._current = self._build(target)
            self._current.load()
            return self._current

    def unload(self) -> None:
        with self._lock:
            if self._current is not None:
                self._current.unload()
                self._current = None
            for e in self._cpu.values():
                e.unload()
            self._cpu = {}
            _empty_cache()

    def refresh_settings(self, settings: Settings) -> None:
        """설정이 바뀌면 현재 엔진을 버려 다음 요청에서 새 값으로 다시 만든다."""
        with self._lock:
            self._settings = settings
            if self._current is not None:
                self._current.unload()
                self._current = None
            self._cpu = {}
            _empty_cache()


def _empty_cache() -> None:
    """torch 가 아직 안 올라왔으면 비울 캐시도 없다."""
    import sys

    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def vram_stats() -> tuple[float | None, float | None, str | None]:
    """(전체 GB, 사용 GB, 장치명). CUDA 가 없으면 (None, None, None).

    torch 를 아직 안 불러왔으면 nvidia-smi 로 대신 읽는다. /health 가 무거운
    임포트를 유발하지 않게 하기 위해서다.
    """
    import sys

    torch = sys.modules.get("torch")
    if torch is None:
        return _vram_from_smi()
    if not torch.cuda.is_available():
        return None, None, None
    free, total = torch.cuda.mem_get_info()
    props = torch.cuda.get_device_properties(0)
    return (
        round(total / 1024 ** 3, 2),
        round((total - free) / 1024 ** 3, 2),
        props.name,
    )


def _vram_from_smi() -> tuple[float | None, float | None, str | None]:
    import subprocess

    try:
        p = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4,
            creationflags=0x08000000,  # 창을 띄우지 않는다
        )
        if p.returncode != 0 or not p.stdout.strip():
            return None, None, None
        total, used, name = [x.strip() for x in p.stdout.strip().splitlines()[0].split(",")]
        return round(float(total) / 1024, 2), round(float(used) / 1024, 2), name
    except Exception:  # noqa: BLE001
        return None, None, None
