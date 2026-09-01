"""인앱 모델 다운로드 — 온보딩의 "내려받기" 버튼이 쓴다.

tools_download_models.py 의 재시도 로직을 작업(Job) 형태로 옮긴 것.
진행률은 디스크에 쌓인 바이트 / 알려진 전체 크기로 계산한다.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from .config import DIA2_MODEL, MIMI_MODEL, MODELS_ROOT, SUPERTONIC_MODEL, VIBEVOICE_MODEL, WHISPER_MODEL

log = logging.getLogger(__name__)

# (대상 경로, HF repo 또는 URL, 대략 크기 GB, 부속물)
CATALOG: dict[str, dict] = {
    "vibevoice": {
        "label": "VibeVoice 1.5B",
        "size_gb": 5.1,
        "parts": [
            {"repo": "microsoft/VibeVoice-1.5B", "dir": VIBEVOICE_MODEL,
             "ignore": ["figures/*", "*.png"]},
            {"repo": "Qwen/Qwen2.5-1.5B", "dir": MODELS_ROOT / "Qwen2.5-1.5B",
             "allow": ["tokenizer.json", "tokenizer_config.json", "vocab.json",
                       "merges.txt", "special_tokens_map.json", "config.json",
                       "generation_config.json"]},
        ],
    },
    "dia2": {
        "label": "Dia2 2B + Mimi",
        "size_gb": 7.6,
        "parts": [
            {"repo": "nari-labs/Dia2-2B", "dir": DIA2_MODEL, "ignore": ["*.gif"]},
            {"repo": "kyutai/mimi", "dir": MIMI_MODEL},
        ],
    },
    "supertonic": {
        "label": "Supertonic 3",
        "size_gb": 0.4,
        "parts": [{"repo": "Supertone/supertonic", "dir": SUPERTONIC_MODEL,
                   "revision": None, "model_name": "supertonic-3"}],
    },
    "whisper": {
        "label": "Whisper large-v3 (클로닝용)",
        "size_gb": 3.1,
        "parts": [{"url": "openai-whisper:large-v3", "dir": WHISPER_MODEL.parent}],
    },
}

_running: set[str] = set()
_running_lock = threading.Lock()


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _snapshot(repo: str, target: Path, allow=None, ignore=None, model_name=None) -> None:  # noqa: ANN001
    from huggingface_hub import snapshot_download

    if model_name:  # supertonic 은 SDK 의 다운로더가 검증까지 해 준다
        from supertonic import TTS

        TTS(model=model_name, model_dir=str(target), auto_download=True)
        return
    for attempt in range(8):
        try:
            snapshot_download(repo_id=repo, local_dir=str(target),
                              allow_patterns=allow, ignore_patterns=ignore,
                              max_workers=4)
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("다운로드 재시도 %d/8 (%s): %s", attempt + 1, repo, exc)
            if attempt == 7:
                raise
            time.sleep(8)


def _openai_whisper(name: str, target_dir: Path) -> None:
    import whisper

    url = whisper._MODELS[name]  # noqa: SLF001
    target_dir.mkdir(parents=True, exist_ok=True)
    dst = target_dir / f"{name}.pt"
    if dst.exists() and dst.stat().st_size > 3_000_000_000:
        return
    import urllib.request

    tmp = dst.with_suffix(".part")
    for attempt in range(8):
        try:
            urllib.request.urlretrieve(url, str(tmp))
            tmp.replace(dst)
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("whisper 다운로드 재시도 %d/8: %s", attempt + 1, exc)
            if attempt == 7:
                raise
            time.sleep(8)


def start(which: str, job) -> None:  # noqa: ANN001
    """job 스레드 안에서 실행된다 (jobs.run 이 부른다)."""
    if which not in CATALOG:
        from .engines.base import EngineError

        raise EngineError("unknown_model", f"모르는 모델입니다: {which}")
    with _running_lock:
        if which in _running:
            from .engines.base import EngineError

            raise EngineError("already_running", "이미 내려받는 중입니다.")
        _running.add(which)

    entry = CATALOG[which]
    total_bytes = int(entry["size_gb"] * 1024 ** 3)
    dirs = [Path(p["dir"]) for p in entry["parts"]]

    stop = threading.Event()

    def reporter() -> None:
        while not stop.wait(1.5):
            got = sum(dir_size(d) for d in dirs)
            frac = min(0.99, got / total_bytes) if total_bytes else 0.0
            job.report(frac * 100, 100, f"{got / 1024**3:.2f} / {entry['size_gb']:.1f} GB")

    t = threading.Thread(target=reporter, daemon=True)
    t.start()
    try:
        for part in entry["parts"]:
            if job.cancelled():
                from .engines.base import EngineError

                raise EngineError("cancelled", "내려받기를 취소했습니다.")
            if "url" in part and part["url"].startswith("openai-whisper:"):
                _openai_whisper(part["url"].split(":", 1)[1], Path(part["dir"]))
            else:
                _snapshot(part["repo"], Path(part["dir"]),
                          allow=part.get("allow"), ignore=part.get("ignore"),
                          model_name=part.get("model_name"))
        job.report(100, 100, "완료")
    finally:
        stop.set()
        with _running_lock:
            _running.discard(which)
