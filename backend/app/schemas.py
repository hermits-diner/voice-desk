"""API 스키마. 대본 JSON 구조는 지침에 고정돼 있다."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

SpeakerId = Literal["NARRATOR", "A", "B", "C", "D"]
ScriptFormat = Literal["Narration", "Conversation", "Interview", "Monologue"]
LengthPreset = Literal["short", "medium", "long"]
Cefr = Literal["A2", "B1", "B2", "C1"]

# 길이 프리셋 -> 목표 단어 수
LENGTH_WORDS: dict[str, int] = {"short": 180, "medium": 420, "long": 900}


class Segment(BaseModel):
    speaker: SpeakerId
    text: str
    note: Optional[str] = None         # 연기 메모 (발화에 넣지 않는다)
    translation: Optional[str] = None  # 한국어 번역 병기 (표시·자막용, 발화 안 함)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("빈 세그먼트는 둘 수 없습니다")
        return v


class Script(BaseModel):
    title: str
    format: ScriptFormat
    segments: list[Segment]

    def speakers(self) -> list[SpeakerId]:
        """등장 순서대로 중복 없이."""
        seen: list[SpeakerId] = []
        for s in self.segments:
            if s.speaker not in seen:
                seen.append(s.speaker)
        return seen


class ScriptRequest(BaseModel):
    topic: str
    format: ScriptFormat = "Conversation"
    length: LengthPreset = "medium"
    level: Cefr = "B1"
    speakers: int = Field(default=2, ge=1, le=4)
    tone: str = "자연스럽고 편안한"
    model: Optional[str] = None  # 설정 기본값을 덮어쓸 때만
    # 세그먼트별 한국어 번역을 함께 받는다 (표시·자막용)
    translate: bool = True
    # 시리즈: 이전 화 대본을 주면 같은 인물·설정으로 이어지는 다음 화를 쓴다
    previous: Optional[Script] = None


class ScriptResponse(BaseModel):
    script: Script
    model: str
    raw: Optional[str] = None  # 파싱 실패 시 원문을 돌려주기 위한 자리


class VoiceAssignment(BaseModel):
    """화자 -> 보이스 프리셋 매핑."""
    speaker: SpeakerId
    voice: str


EngineId = Literal["vibevoice", "dia2", "supertonic"]


class RenderRequest(BaseModel):
    script: Script
    engine: Optional[EngineId] = None
    voices: list[VoiceAssignment] = Field(default_factory=list)
    # 이 세그먼트 인덱스만 다시 합성한다 (Dia2 세그먼트 캐시 경로)
    resynth_only: Optional[list[int]] = None
    seed: Optional[int] = None
    # Dia2 레퍼런스 클로닝: 화자 -> 레퍼런스 wav 경로 (최대 2명)
    references: Optional[dict[str, str]] = None
    # 실험: 이 인덱스부터만 다시 렌더하고 앞부분은 이전 오디오를 재사용한다
    resume_from: Optional[int] = None
    prev_audio_path: Optional[str] = None
    prev_timings: Optional[list["SegmentTiming"]] = None


class TtsRequest(BaseModel):
    """빠른 변환 탭 — 단일 화자 단문."""
    text: str
    voice: Optional[str] = None
    engine: Optional[EngineId] = None


class SegmentTiming(BaseModel):
    index: int
    speaker: SpeakerId
    text: str
    start: float
    end: float
    translation: Optional[str] = None


class Voice(BaseModel):
    id: str
    label: str
    language: str
    gender: Optional[str] = None
    engine: Literal["vibevoice", "dia2", "supertonic", "any"] = "vibevoice"
    has_bgm: bool = False
    path: Optional[str] = None


JobState = Literal["queued", "loading", "running", "encoding", "done", "error", "cancelled"]


class JobStatus(BaseModel):
    id: str
    state: JobState
    kind: Literal["render", "tts"]
    progress: float = 0.0            # 0.0 ~ 1.0
    step: int = 0
    total_steps: int = 0
    segment_index: Optional[int] = None   # Dia2 세그먼트 진행률
    segment_total: Optional[int] = None
    message: str = ""
    started_at: Optional[float] = None
    elapsed: float = 0.0
    eta: Optional[float] = None
    # 완료 시
    audio_path: Optional[str] = None
    script_path: Optional[str] = None
    timing_path: Optional[str] = None
    duration: Optional[float] = None
    timings: Optional[list[SegmentTiming]] = None
    # 실패 시 — 원인과 다음 행동을 한 문장으로
    error_code: Optional[str] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    engine: str
    engine_loaded: Optional[str]
    cuda: bool
    device: Optional[str] = None
    vram_total_gb: Optional[float] = None
    vram_used_gb: Optional[float] = None
    models: dict[str, bool]
    has_gemini_key: bool
