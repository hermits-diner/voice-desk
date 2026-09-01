"""경로 · 기본값 설정.

경로는 전부 ASCII 로 유지한다 (한글 · 공백 금지 제약).
출력 폴더만 예외로 %USERPROFILE%\\Music\\VoiceDesk 를 쓰는데, 여기는
ffmpeg 에 넘길 때 항상 인용하고 파일 쓰기 외의 용도로 쓰지 않는다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

AI_ROOT = Path(r"C:\ai")
MODELS_ROOT = AI_ROOT / "models"
BACKEND_ROOT = Path(__file__).resolve().parent.parent
THIRD_PARTY = BACKEND_ROOT / "third_party"

# HF 캐시가 한글 경로로 가지 않게 프로세스 진입 시점에 고정한다.
os.environ.setdefault("HF_HOME", str(MODELS_ROOT / "hf-cache"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

FFMPEG = BACKEND_ROOT / "bin" / "ffmpeg.exe"
FFPROBE = BACKEND_ROOT / "bin" / "ffprobe.exe"

# whisper(레퍼런스 클로닝 전사)가 PATH 의 ffmpeg 를 부른다. 동봉본을 앞에 세운다.
os.environ["PATH"] = str(BACKEND_ROOT / "bin") + os.pathsep + os.environ.get("PATH", "")

VIBEVOICE_MODEL = MODELS_ROOT / "VibeVoice-1.5B"
VIBEVOICE_VOICES = THIRD_PARTY / "VibeVoice" / "demo" / "voices"
DIA2_MODEL = MODELS_ROOT / "Dia2-2B"
MIMI_MODEL = MODELS_ROOT / "mimi"
SUPERTONIC_MODEL = MODELS_ROOT / "supertonic-3"
WHISPER_MODEL = MODELS_ROOT / "whisper" / "large-v3.pt"

SETTINGS_PATH = BACKEND_ROOT / "settings.json"

EngineName = Literal["vibevoice", "dia2", "supertonic"]

# 자격 증명 관리자에 쓰는 서비스 이름. 값은 절대 로그에 남기지 않는다.
KEYRING_SERVICE = "voice-desk"
KEY_GEMINI = "gemini_api_key"
KEY_HF = "hf_token"


class Settings(BaseModel):
    """앱 설정. settings.json 에 저장되며 비밀값은 여기에 들어오지 않는다."""

    host: str = "127.0.0.1"
    port: int = 7860

    engine: EngineName = "vibevoice"
    output_dir: str = Field(
        default_factory=lambda: str(Path(os.environ["USERPROFILE"]) / "Music" / "VoiceDesk")
    )

    # 오디오
    audio_format: Literal["mp3", "wav"] = "mp3"
    bitrate_kbps: int = 128
    loudness_lufs: float = -16.0
    sample_rate: int = 24000
    gap_speaker_ms: int = 500   # 화자 전환 무음
    gap_paragraph_ms: int = 800  # 문단 전환 무음

    # VibeVoice
    vv_ddpm_steps: int = 10
    vv_cfg_scale: float = 1.3
    # 발화 뒤에 따라붙는 금속성 잔향(3.5~9kHz 협대역 톤) 정리. audio.polish 참조.
    vv_polish: bool = True

    # Dia2
    dia2_cuda_graph: bool = True   # 끄면 Windows 에서 4배 느려진다
    dia2_temperature: float = 0.8
    dia2_top_k: int = 50
    dia2_cfg_scale: float = 1.0
    dia2_max_retries: int = 2      # 발산 출력 감지 시 재시드 횟수

    # Supertonic (한국어 · 다국어 CPU 엔진)
    supertonic_lang: str = "ko"       # "na" 면 언어 자동
    supertonic_speed: float = 1.05
    supertonic_steps: int = 8

    # 내보내기
    export_subtitles: bool = True     # mp3 옆에 .srt 를 함께 만든다
    script_translation: bool = True   # 대본 생성 시 한국어 번역 병기

    # Gemini — 모델명은 설정에서 바꿀 수 있고, /gemini/models 로 실제 목록을 조회한다.
    # 2026-09-01 실측: 목록상 최신은 gemini-3.7-flash 이지만 계속 503(과부하)이 떴고
    # gemini-3.6-flash 는 안정적으로 응답했다. 실제로 응답하는 최신 Flash 를 기본으로 둔다.
    # 설정 화면의 "목록 받기" 로 현재 쓸 수 있는 모델을 다시 확인할 수 있다.
    gemini_model: str = "gemini-3.6-flash"

    theme: Literal["system", "dark", "light"] = "system"

    @classmethod
    def load(cls) -> "Settings":
        if SETTINGS_PATH.exists():
            try:
                return cls.model_validate_json(SETTINGS_PATH.read_text("utf-8"))
            except Exception:
                # 손상된 설정 때문에 서버가 못 뜨는 상황을 만들지 않는다.
                pass
        return cls()

    def save(self) -> None:
        SETTINGS_PATH.write_text(
            json.dumps(self.model_dump(), indent=2, ensure_ascii=False), "utf-8"
        )


def model_status() -> dict[str, bool]:
    """가중치가 실제로 있는지. 온보딩과 /health 가 쓴다."""
    return {
        "vibevoice": (VIBEVOICE_MODEL / "model.safetensors.index.json").exists(),
        "dia2": (DIA2_MODEL / "model.safetensors").exists(),
        "mimi": (MIMI_MODEL / "model.safetensors").exists(),
        "supertonic": (SUPERTONIC_MODEL / "onnx").exists(),
        "whisper": WHISPER_MODEL.exists(),
        "ffmpeg": FFMPEG.exists(),
    }
