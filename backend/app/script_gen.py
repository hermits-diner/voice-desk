"""Gemini 대본 생성.

JSON 만 돌려받도록 응답 스키마를 걸고, 파싱 실패 시 1회 재요청한다.
그래도 실패하면 원문을 그대로 올려보내 사용자가 고치게 한다 (지침 4).
"""
from __future__ import annotations

import json
import logging
import re
import time

from .schemas import LENGTH_WORDS, Script, ScriptRequest
from .secrets_store import get_gemini_key, redact

log = logging.getLogger(__name__)

# 대본 JSON 스키마 — 지침에 고정돼 있고, translation 은 표시·자막용 확장이다.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "format": {"type": "string"},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {
                        "type": "string",
                        "enum": ["NARRATOR", "A", "B", "C", "D"],
                    },
                    "text": {"type": "string"},
                    "note": {"type": "string", "nullable": True},
                    "translation": {"type": "string", "nullable": True},
                },
                "required": ["speaker", "text"],
            },
        },
    },
    "required": ["title", "format", "segments"],
}

SYSTEM = """You write scripts that will be spoken aloud by a text-to-speech engine.

Rules:
- Output JSON only. No markdown fences, no commentary.
- "text" must be speakable prose. No stage directions inside text, no bullet
  points, no numbered lists, no markdown, no emoji, no URLs.
- Put delivery hints in "note" instead: a short phrase such as "warm, unhurried"
  or "surprised". Use note sparingly, only where it changes the read. Otherwise null.
- Write out numbers, symbols and abbreviations the way they are said aloud.
- Keep each segment to one speaker's continuous turn. Split long turns.
- For NARRATION and MONOLOGUE use only the NARRATOR speaker.
- For CONVERSATION and INTERVIEW use A, B, C, D in that order, never skipping.
"""


class ScriptGenError(RuntimeError):
    def __init__(self, code: str, message: str, raw: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.raw = raw


def _client():
    key = get_gemini_key()
    if not key:
        raise ScriptGenError(
            "no_key", "Gemini 키가 없습니다. 설정에서 키를 등록해주세요."
        )
    from google import genai

    return genai.Client(api_key=key)


def _prompt(req: ScriptRequest) -> str:
    words = LENGTH_WORDS[req.length]
    if req.format in ("Narration", "Monologue"):
        speaker_line = "Use only NARRATOR."
    else:
        labels = ", ".join(["A", "B", "C", "D"][: req.speakers])
        speaker_line = f"Use exactly {req.speakers} speakers: {labels}."

    parts = [
        f"Topic or situation: {req.topic}",
        f"Format: {req.format}",
        f"Target length: about {words} words in total.",
        f"Language level: CEFR {req.level}. Match vocabulary and sentence length to it.",
        speaker_line,
        f"Tone: {req.tone}",
    ]

    if req.translate:
        parts.append(
            "For every segment, put a natural Korean translation of that segment's "
            "text in 'translation'. If the script itself is in Korean, set "
            "translation to null."
        )
    else:
        parts.append("Set 'translation' to null for every segment.")

    if req.previous is not None and req.previous.segments:
        prev_lines = "\n".join(
            f"[{s.speaker}] {s.text}" for s in req.previous.segments
        )
        parts.append(
            "This is the NEXT EPISODE of an ongoing series. Previous episode "
            f"(title: {req.previous.title!r}):\n{prev_lines}\n"
            "Keep the same speakers, personalities and situation. Continue the "
            "story naturally — reference what happened, do not repeat it."
        )

    parts.append("Give the script a short title in the same language as the script.")
    return "\n".join(parts)


def _extract_json(text: str) -> dict:
    """모델이 코드펜스나 잡담을 붙였을 때를 대비한 관대한 파서."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        return json.loads(t[start:end + 1])
    raise json.JSONDecodeError("JSON 을 찾지 못했습니다", t, 0)


def _normalize(data: dict, req: ScriptRequest) -> dict:
    data.setdefault("format", req.format)
    if data.get("format") not in ("Narration", "Conversation", "Interview", "Monologue"):
        data["format"] = req.format
    data.setdefault("title", req.topic[:60])
    segs = []
    for s in data.get("segments") or []:
        if not isinstance(s, dict):
            continue
        text = (s.get("text") or "").strip()
        if not text:
            continue
        sp = (s.get("speaker") or "NARRATOR").upper()
        if sp not in ("NARRATOR", "A", "B", "C", "D"):
            sp = "NARRATOR"
        note = s.get("note")
        if isinstance(note, str) and not note.strip():
            note = None
        tr = s.get("translation")
        if isinstance(tr, str) and not tr.strip():
            tr = None
        segs.append({"speaker": sp, "text": text, "note": note, "translation": tr})
    data["segments"] = segs
    return data


def _classify(exc: Exception, model: str) -> ScriptGenError:
    """API 예외를 사용자가 읽을 한 문장으로 바꾼다.

    원본 메시지에는 JSON 이 통째로 들어 있어 그대로 보여주면 읽히지 않는다.
    """
    msg = redact(str(exc))
    low = msg.lower()
    if "api key" in low or "unauthenticated" in low or "permission" in low or "401" in low:
        return ScriptGenError("bad_key", "Gemini 키가 거부됐습니다. 설정에서 키를 확인해주세요.")
    if "not found" in low or "404" in low:
        return ScriptGenError(
            "bad_model", f"모델 '{model}' 을 찾을 수 없습니다. 설정에서 다른 모델을 골라주세요."
        )
    if "429" in low or "quota" in low or "resource_exhausted" in low:
        return ScriptGenError("quota", "Gemini 사용 한도에 걸렸습니다. 잠시 뒤 다시 시도해주세요.")
    if _is_transient(exc):
        return ScriptGenError(
            "busy", "Gemini 서버가 지금 붐빕니다. 잠시 뒤 다시 눌러주세요."
        )
    # 알 수 없는 오류만 원문 일부를 붙인다
    return ScriptGenError("api", f"Gemini 호출이 실패했습니다. {msg[:120]}")


def _is_transient(exc: Exception) -> bool:
    low = str(exc).lower()
    return (
        "503" in low
        or "unavailable" in low
        or "overloaded" in low
        or "500" in low
        or "internal error" in low
        or "deadline" in low
        or "timeout" in low
    )


def _call(client, model: str, prompt: str, config):  # noqa: ANN001
    """일시적 오류(503 등)는 물러서며 다시 시도한다.

    503 UNAVAILABLE 은 모델이 붐빌 때 흔히 나고 대개 몇 초 뒤에 풀린다.
    이런 것까지 사용자에게 던지면 앱이 불안정해 보인다.
    """
    delays = [1.5, 4.0, 8.0]
    last: Exception | None = None
    for i in range(len(delays) + 1):
        try:
            return client.models.generate_content(model=model, contents=prompt, config=config)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if not _is_transient(exc) or i == len(delays):
                raise
            log.warning("Gemini 일시 오류, %.1f초 뒤 재시도 (%d/%d)", delays[i], i + 1, len(delays))
            time.sleep(delays[i])
    raise last  # type: ignore[misc]


def generate(req: ScriptRequest, model: str) -> tuple[Script, str | None]:
    """(대본, 원문) 을 돌려준다. 성공하면 원문은 None."""
    from google.genai import types

    client = _client()
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
        temperature=0.9,
    )
    prompt = _prompt(req)

    last_raw = ""
    for attempt in range(2):  # 파싱 실패 시 1회 재요청
        try:
            resp = _call(client, model, prompt, config)
        except Exception as exc:  # noqa: BLE001
            raise _classify(exc, model) from exc

        last_raw = (resp.text or "").strip()
        try:
            data = _normalize(_extract_json(last_raw), req)
            script = Script.model_validate(data)
            if not script.segments:
                raise ValueError("세그먼트가 비어 있습니다")
            return script, None
        except Exception as exc:  # noqa: BLE001
            log.warning("대본 파싱 실패 (시도 %d): %s", attempt + 1, exc)
            if attempt == 0:
                prompt = _prompt(req) + (
                    "\n\nYour previous reply could not be parsed as the required JSON. "
                    "Reply again with valid JSON only."
                )

    raise ScriptGenError(
        "parse", "대본 형식을 두 번 다 읽지 못했습니다. 원문을 보고 고쳐주세요.", raw=last_raw
    )


SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "note": {"type": "string", "nullable": True},
        "translation": {"type": "string", "nullable": True},
    },
    "required": ["text"],
}


def regenerate_segment(
    script: Script, index: int, model: str
) -> tuple[str, str | None, str | None]:
    """앞뒤 맥락을 주고 한 줄만 다시 쓴다.

    대본 전체를 다시 만들면 사용자가 손본 다른 줄까지 날아간다.
    """
    from google.genai import types

    if not 0 <= index < len(script.segments):
        raise ScriptGenError("bad_index", "그 구간이 없습니다.")

    target = script.segments[index]
    lines = []
    for i, s in enumerate(script.segments):
        marker = "  <-- REWRITE THIS LINE" if i == index else ""
        lines.append(f"{i}. [{s.speaker}] {s.text}{marker}")
    context = "\n".join(lines)

    prompt = (
        f'Script title: "{script.title}"\nFormat: {script.format}\n\n'
        f"{context}\n\n"
        f"Rewrite only line {index}, spoken by {target.speaker}. Keep it roughly the "
        "same length and the same role in the conversation, but say it differently. "
        "It must still fit naturally between the lines around it. "
        "Return JSON with 'text', optional 'note', and 'translation' (a natural "
        "Korean translation of the new text; null if the text is already Korean)."
    )

    client = _client()
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        response_schema=SEGMENT_SCHEMA,
        temperature=1.0,  # 같은 문장이 다시 나오지 않게 조금 높인다
    )
    try:
        resp = _call(client, model, prompt, config)
    except Exception as exc:  # noqa: BLE001
        raise _classify(exc, model) from exc

    try:
        data = _extract_json((resp.text or "").strip())
        text = (data.get("text") or "").strip()
        if not text:
            raise ValueError("빈 텍스트")
        note = data.get("note")
        if isinstance(note, str) and not note.strip():
            note = None
        tr = data.get("translation")
        if isinstance(tr, str) and not tr.strip():
            tr = None
        return text, note, tr
    except Exception as exc:  # noqa: BLE001
        raise ScriptGenError("parse", "돌려받은 내용을 읽지 못했습니다. 다시 시도해주세요.") from exc


def list_models() -> list[str]:
    """generateContent 를 지원하는 모델 목록.

    모델명은 계속 바뀌므로 하드코딩하지 않고 API 에서 받아 온다.
    """
    client = _client()
    out: list[str] = []
    try:
        for m in client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            name = (m.name or "").removeprefix("models/")
            if name:
                out.append(name)
    except Exception as exc:  # noqa: BLE001
        raise ScriptGenError("api", f"모델 목록을 받지 못했습니다: {redact(str(exc))[:200]}") from exc
    return sorted(out)
