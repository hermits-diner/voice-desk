"""Windows 자격 증명 관리자 래퍼.

비밀값은 여기를 통해서만 오간다. 값은 반환만 하고 절대 로그 · 예외 메시지에
넣지 않는다. 존재 여부만 노출한다.
"""
from __future__ import annotations

import keyring

from .config import KEY_GEMINI, KEY_HF, KEYRING_SERVICE


def _get(name: str) -> str | None:
    try:
        v = keyring.get_password(KEYRING_SERVICE, name)
    except Exception:
        return None
    return v or None


def _set(name: str, value: str) -> None:
    keyring.set_password(KEYRING_SERVICE, name, value)


def _delete(name: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass


def get_gemini_key() -> str | None:
    return _get(KEY_GEMINI)


def set_gemini_key(value: str) -> None:
    value = value.strip()
    if not value:
        raise ValueError("빈 키는 저장하지 않습니다")
    _set(KEY_GEMINI, value)


def clear_gemini_key() -> None:
    _delete(KEY_GEMINI)


def has_gemini_key() -> bool:
    return get_gemini_key() is not None


def get_hf_token() -> str | None:
    return _get(KEY_HF)


def set_hf_token(value: str) -> None:
    _set(KEY_HF, value.strip())


def redact(text: str) -> str:
    """예외 메시지에 키가 섞여 나오는 사고를 막는 마지막 방어선."""
    out = text
    for v in (get_gemini_key(), get_hf_token()):
        if v and len(v) >= 8:
            out = out.replace(v, "***")
    return out
