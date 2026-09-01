"""보이스 프리셋 레지스트리.

VibeVoice 는 레퍼런스 wav 를 프리필해 음색을 잡는다. 포크가 제공하는 9종을
기본으로 싣고, 사용자가 추가한 wav 는 C:\\ai\\models\\voices 에서 읽는다.

Dia2 는 프리셋 wav 를 쓰지 않는다 (프리픽스 클로닝은 별도 기능이고 현재 미구현).
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import MODELS_ROOT, VIBEVOICE_VOICES
from .schemas import Voice

USER_VOICES = MODELS_ROOT / "voices"

_LANG = {
    "en": "영어",
    "zh": "중국어",
    "in": "인도 영어",
    "kr": "한국어",
    "jp": "일본어",
    "de": "독일어",
    "fr": "프랑스어",
    "es": "스페인어",
    "sp": "스페인어",
    "it": "이탈리아어",
    "nl": "네덜란드어",
    "pl": "폴란드어",
    "pt": "포르투갈어",
}

# 파일명 규약: <lang>-<Name>_<gender>[_bgm].wav  예) en-Alice_woman.wav
_PATTERN = re.compile(r"^(?P<lang>[a-z]{2})-(?P<name>[^_]+)_(?P<gender>man|woman)(?P<bgm>_bgm)?$")


def _parse(path: Path) -> Voice:
    stem = path.stem
    m = _PATTERN.match(stem)
    if m:
        lang = _LANG.get(m["lang"], m["lang"])
        gender = "여성" if m["gender"] == "woman" else "남성"
        bgm = bool(m["bgm"])
        label = f"{m['name']} · {lang} {gender}" + (" · 배경음 포함" if bgm else "")
        return Voice(
            id=stem, label=label, language=lang, gender=gender,
            engine="vibevoice", has_bgm=bgm, path=str(path),
        )
    # 사용자가 넣은 임의 파일명
    return Voice(
        id=stem, label=stem, language="사용자 추가",
        engine="vibevoice", path=str(path),
    )


def list_voices() -> list[Voice]:
    found: dict[str, Voice] = {}
    for root in (VIBEVOICE_VOICES, USER_VOICES):
        if not root.exists():
            continue
        for wav in sorted(root.glob("*.wav")):
            v = _parse(wav)
            found[v.id] = v  # 사용자 폴더가 같은 이름이면 덮어쓴다

    # Supertonic 스타일 (모델이 설치돼 있을 때만)
    from .engines.supertonic_engine import voice_catalog

    for d in voice_catalog():
        found[d["id"]] = Voice(**d)
    return list(found.values())


def resolve(voice_id: str | None) -> Path:
    """보이스 id -> wav 경로. 없으면 첫 번째 보이스로 떨어진다."""
    voices = list_voices()
    if not voices:
        raise FileNotFoundError(
            "보이스 파일이 없습니다. third_party/VibeVoice 가 설치됐는지 확인해주세요."
        )
    if voice_id:
        for v in voices:
            if v.id == voice_id:
                return Path(v.path)  # type: ignore[arg-type]
        low = voice_id.lower()
        for v in voices:
            if low in v.id.lower():
                return Path(v.path)  # type: ignore[arg-type]
    return Path(voices[0].path)  # type: ignore[arg-type]


def default_assignment(speakers: list[str]) -> dict[str, str]:
    """화자 목록에 서로 다른 보이스를 성별 번갈아 배정한다."""
    pool = [v for v in list_voices() if not v.has_bgm and v.language == "영어"]
    if not pool:
        pool = list_voices()
    women = [v for v in pool if v.gender == "여성"]
    men = [v for v in pool if v.gender == "남성"]
    order: list[Voice] = []
    for i in range(max(len(women), len(men))):
        if i < len(women):
            order.append(women[i])
        if i < len(men):
            order.append(men[i])
    if not order:
        order = pool
    return {sp: order[i % len(order)].id for i, sp in enumerate(speakers)}
