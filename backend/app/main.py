"""VoiceDesk 백엔드 — 127.0.0.1 에서만 수신한다."""
from __future__ import annotations

import json
import logging
import os
import re
import signal
import threading
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import audio as A
from . import script_gen, secrets_store, voices
from .config import Settings, model_status
from .engines.base import EngineError
from .engines.manager import EngineManager, vram_stats
from .jobs import Job, JobRegistry
from .schemas import (
    HealthResponse, JobStatus, RenderRequest, Script, ScriptRequest,
    ScriptResponse, TtsRequest, Voice,
)

VERSION = "0.1.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("voicedesk")

settings = Settings.load()
engines = EngineManager(settings)
jobs = JobRegistry()

app = FastAPI(title="VoiceDesk", version=VERSION)
# 서버가 127.0.0.1 에만 바인딩되므로 출처는 로컬 개발 서버와 Tauri 웹뷰뿐이다.
# Vite 포트를 바꿀 때마다 여기가 어긋나는 사고를 막으려고 정규식으로 받는다.
# (Windows 의 Tauri 2 웹뷰 출처는 http://tauri.localhost 이다)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost|https?://tauri\.localhost)$",
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- 파일 이름

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_stem(title: str, fmt: str) -> str:
    """날짜_제목_형식 — Windows 금지 문자와 길이를 정리한다."""
    t = _BAD.sub("", title).strip().strip(".")
    t = re.sub(r"\s+", " ", t)[:60].strip() or "무제"
    return f"{date.today():%Y%m%d}_{t}_{fmt}"


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{stem}.{ext}"
    n = 2
    while p.exists():
        p = folder / f"{stem} ({n}).{ext}"
        n += 1
    return p


def write_outputs(job: Job, script: Script, result, fmt: str, engine_name: str) -> None:
    """wav -> 인코딩, 대본 txt, 타임스탬프 json, 자막(srt/vtt)을 나란히 쓴다."""
    out_dir = Path(settings.output_dir)
    stem = safe_stem(script.title, script.format)

    tmp_wav = out_dir / f".{stem}.tmp.wav"
    A.write_wav(tmp_wav, result.audio, result.sample_rate)
    try:
        job.set_state("encoding", "인코딩 중")
        dst = unique_path(out_dir, stem, fmt)
        A.encode(
            tmp_wav, dst, fmt=fmt, bitrate_kbps=settings.bitrate_kbps,
            lufs=settings.loudness_lufs,
            # 엔진 고유 샘플레이트를 유지한다 (supertonic 44.1kHz, 나머지 24kHz)
            sample_rate=result.sample_rate,
            # VibeVoice 는 구절 사이에 금속성 잔향이 붙는다. 조용한 구간만
            # 낮추는 익스팬더로 정규화 게인이 잔향을 키우는 것을 막는다.
            expand_quiet=(engine_name == "vibevoice" and settings.vv_polish),
        )
    finally:
        tmp_wav.unlink(missing_ok=True)

    # 제목에 마침표가 있으면 with_suffix 가 엉뚱한 곳을 자르므로 문자열로 붙인다
    base = str(dst)[: -len(dst.suffix)] if dst.suffix else str(dst)
    txt = Path(base + ".txt")
    lines = []
    for t in result.timings:
        lines.append(f"[{t.speaker}] {t.text}" +
                     (f"\n    {t.translation}" if t.translation else ""))
    txt.write_text("\n\n".join(lines), encoding="utf-8")

    if settings.export_subtitles:
        A.write_srt(Path(base + ".srt"), result.timings)
        A.write_vtt(Path(base + ".vtt"), result.timings)

    tj = Path(base + ".json")
    tj.write_text(json.dumps({
        "title": script.title,
        "format": script.format,
        "engine": engine_name,
        "sample_rate": result.sample_rate,
        "duration": round(len(result.audio) / result.sample_rate, 3),
        "timings_estimated": result.timings_estimated,
        "timing_notes": result.notes,
        "segments": [t.model_dump() for t in result.timings],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    job.audio_path = str(dst)
    job.script_path = str(txt)
    job.timing_path = str(tj)
    job.timings = result.timings
    job.duration = round(len(result.audio) / result.sample_rate, 3)


# ---------------------------------------------------------------- 엔드포인트


@app.get("/")
def root() -> dict:
    """브라우저로 주소를 직접 열었을 때 'Not Found' 대신 안내를 보여준다.

    이 서버는 VoiceDesk 앱이 쓰는 API 라 사람이 볼 화면은 없다.
    """
    return {
        "app": "VoiceDesk backend",
        "version": VERSION,
        "notice": "이 주소는 VoiceDesk 앱이 내부적으로 쓰는 API 서버입니다. "
                  "화면은 VoiceDesk 앱에서 열어주세요.",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    total, used, device = vram_stats()
    models = model_status()
    ok = models["ffmpeg"] and (models["vibevoice"] or models["dia2"]) and device is not None
    return HealthResponse(
        status="ok" if ok else "degraded",
        version=VERSION,
        engine=settings.engine,
        engine_loaded=engines.loaded_name,
        cuda=device is not None,
        device=device,
        vram_total_gb=total,
        vram_used_gb=used,
        models=models,
        has_gemini_key=secrets_store.has_gemini_key(),
    )


@app.get("/voices", response_model=list[Voice])
def get_voices() -> list[Voice]:
    return voices.list_voices()


_HTTP_FOR: dict[str, int] = {
    "no_key": 401, "bad_key": 401,
    "quota": 429, "busy": 503,
    "bad_model": 400, "bad_index": 400,
}


def _script_http(exc: script_gen.ScriptGenError) -> HTTPException:
    if exc.code == "parse":
        # 원문을 돌려주고 사용자가 고치게 한다 (지침 4)
        return HTTPException(
            422, detail={"code": exc.code, "message": exc.message, "raw": exc.raw}
        )
    return HTTPException(
        _HTTP_FOR.get(exc.code, 502), detail={"code": exc.code, "message": exc.message}
    )


@app.post("/script", response_model=ScriptResponse)
def make_script(req: ScriptRequest) -> ScriptResponse:
    model = req.model or settings.gemini_model
    if not settings.script_translation:
        req = req.model_copy(update={"translate": False})
    try:
        script, raw = script_gen.generate(req, model)
    except script_gen.ScriptGenError as exc:
        raise _script_http(exc) from exc
    return ScriptResponse(script=script, model=model, raw=raw)


@app.post("/script/segment")
def regenerate_segment(body: dict) -> dict:
    """대본 한 줄만 다시 쓴다. 나머지 줄은 건드리지 않는다."""
    try:
        script = Script.model_validate(body.get("script") or {})
        index = int(body.get("index", -1))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, detail={"code": "bad_body", "message": "요청이 올바르지 않습니다."}) from exc

    model = body.get("model") or settings.gemini_model
    try:
        text, note, translation = script_gen.regenerate_segment(script, index, model)
    except script_gen.ScriptGenError as exc:
        raise _script_http(exc) from exc
    if not settings.script_translation:
        translation = None
    return {"text": text, "note": note, "translation": translation}


@app.get("/gemini/models", response_model=list[str])
def gemini_models() -> list[str]:
    try:
        return script_gen.list_models()
    except script_gen.ScriptGenError as exc:
        raise _script_http(exc) from exc


@app.post("/render", response_model=JobStatus)
def render(req: RenderRequest) -> JobStatus:
    if not req.script.segments:
        raise HTTPException(400, detail={"code": "empty", "message": "대본이 비어 있습니다."})

    engine_name = req.engine or settings.engine
    voice_map = {v.speaker: v.voice for v in req.voices}
    if not voice_map:
        voice_map = voices.default_assignment(list(req.script.speakers()))

    job = jobs.create("render")
    # 구간 진행률은 줄 단위로 합성하는 엔진(Dia2)만 보고한다. VibeVoice 는 대본
    # 전체를 한 번에 렌더해서 중간 구간 번호가 없으므로 여기서 미리 채우지 않는다.
    # 채워두면 UI 에 0/13 이 계속 떠서 멈춘 것처럼 보인다.

    def work(j: Job) -> None:
        j.set_state("loading", "모델을 올리는 중")
        engine = engines.get(engine_name)
        j.set_state("running", "합성 시작")

        def on_progress(done_s: float, total_s: float, msg: str) -> None:
            j.report(done_s, total_s, msg)
            m = re.match(r"(\d+)/(\d+)번째", msg)
            if m:
                j.set_segment(int(m.group(1)), int(m.group(2)))

        # 실험: 이 인덱스부터만 다시 렌더 (앞부분은 이전 오디오 재사용)
        resume = req.resume_from
        target_script = req.script
        if (resume and resume > 0 and req.prev_audio_path and req.prev_timings
                and resume < len(req.script.segments)
                and len(req.prev_timings) >= resume):
            target_script = Script(
                title=req.script.title, format=req.script.format,
                segments=req.script.segments[resume:],
            )

        kwargs: dict = {}
        if engine_name == "dia2" and req.references:
            kwargs["references"] = req.references

        result = engine.render(
            target_script, voice_map,
            on_progress=on_progress, should_cancel=j.cancelled, seed=req.seed,
            on_audio=j.push_pcm, **kwargs,
        )

        if target_script is not req.script:
            result = _splice_resume(req, result)

        write_outputs(j, req.script, result, settings.audio_format, engine_name)
        note = " ".join(result.notes)
        j.set_state("encoding", note or "저장 중")

    jobs.run(job, work)
    return job.status()


def _splice_resume(req: RenderRequest, result):  # noqa: ANN001, ANN202
    """부분 재렌더: 이전 오디오의 앞부분 + 새로 합성한 뒷부분을 잇는다.

    이음새에서 목소리 톤이 미세하게 튈 수 있어 실험 기능으로 표시한다.
    """
    import numpy as np

    n = req.resume_from or 0
    sr = result.sample_rate
    prev = A.load_audio(Path(req.prev_audio_path), sr)
    cut_at = req.prev_timings[n - 1].end
    head = prev[: int(cut_at * sr)]
    merged = A.crossfade_concat(head, np.asarray(result.audio).reshape(-1), sr)

    offset = len(head) / sr
    timings = [t.model_copy() for t in req.prev_timings[:n]]
    for t in result.timings:
        timings.append(t.model_copy(update={
            "index": t.index + n,
            "start": round(t.start + offset, 3),
            "end": round(t.end + offset, 3),
        }))
    result.audio = merged
    result.timings = timings
    result.timings_estimated = True
    result.notes = [*result.notes,
                    f"{n + 1}번째 구간부터 다시 합성해 이어 붙였습니다 (실험 기능)."]
    return result


@app.post("/tts", response_model=JobStatus)
def tts(req: TtsRequest) -> JobStatus:
    text = req.text.strip()
    if not text:
        raise HTTPException(400, detail={"code": "empty", "message": "텍스트가 비어 있습니다."})

    script = Script(
        title=text[:40],
        format="Monologue",
        segments=[{"speaker": "NARRATOR", "text": text}],  # type: ignore[list-item]
    )
    engine_name = req.engine or settings.engine
    voice_map = {"NARRATOR": req.voice} if req.voice else voices.default_assignment(["NARRATOR"])

    job = jobs.create("tts")

    def work(j: Job) -> None:
        j.set_state("loading", "모델을 올리는 중")
        engine = engines.get(engine_name)
        j.set_state("running", "합성 시작")
        result = engine.render(
            script, voice_map,  # type: ignore[arg-type]
            on_progress=lambda d, t, m: j.report(d, t, m),
            should_cancel=j.cancelled, seed=None, on_audio=j.push_pcm,
        )
        write_outputs(j, script, result, settings.audio_format, engine_name)

    jobs.run(job, work)
    return job.status()


@app.get("/jobs", response_model=list[JobStatus])
def jobs_list() -> list[JobStatus]:
    """최근 작업 목록 — 배치 큐 표시용."""
    return [j.status() for j in jobs.recent()]


@app.get("/jobs/{job_id}/pcm")
def job_pcm(job_id: str, from_byte: int = 0):  # noqa: ANN201
    """렌더 중 미리 듣기 — from_byte 이후의 새 int16 PCM 만 준다."""
    from fastapi import Response

    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail={"code": "no_job", "message": "그런 작업이 없습니다."})
    data, total, sr = job.read_pcm(from_byte)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "X-Pcm-Total": str(total),
            "X-Pcm-Sr": str(sr or 0),
            "X-Job-State": job.state,
        },
    )


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str) -> JobStatus:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail={"code": "no_job", "message": "그런 작업이 없습니다."})
    return job.status()


@app.post("/jobs/{job_id}/cancel", response_model=JobStatus)
def job_cancel(job_id: str) -> JobStatus:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail={"code": "no_job", "message": "그런 작업이 없습니다."})
    job.cancel()
    return job.status()


@app.get("/jobs/{job_id}/audio")
def job_audio(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if job is None or not job.audio_path or not Path(job.audio_path).exists():
        raise HTTPException(404, detail={"code": "no_audio", "message": "오디오가 아직 없습니다."})
    return FileResponse(job.audio_path)


@app.get("/audio")
def audio_file(path: str) -> FileResponse:
    """히스토리에서 다시 연 항목의 저장본 재생. 출력 폴더 밖은 주지 않는다."""
    p = Path(path).resolve()
    out = Path(settings.output_dir).resolve()
    if not p.is_file() or out not in p.parents:
        raise HTTPException(404, detail={"code": "no_audio", "message": "그 파일이 없습니다."})
    return FileResponse(str(p))


# ------------------------------------------------------------ 보이스 미리듣기

PREVIEW_DIR = Path(__file__).resolve().parent.parent / "cache" / "voice_previews"
PREVIEW_TEXT_EN = "This is how this voice sounds. Short sample, nothing more."
PREVIEW_TEXT_KO = "이 목소리는 이렇게 들립니다. 짧은 샘플입니다."


@app.get("/voices/{voice_id}/preview")
def voice_preview(voice_id: str) -> FileResponse:
    """보이스 샘플. 처음 한 번만 합성하고 이후에는 캐시로 즉시 준다."""
    safe = _BAD.sub("", voice_id)[:60]
    cached = PREVIEW_DIR / f"{safe}.mp3"
    if cached.exists():
        return FileResponse(str(cached))

    from .jobs import GPU_LOCK

    is_st = voice_id.startswith("st-")
    if not GPU_LOCK.acquire(blocking=False):
        raise HTTPException(409, detail={
            "code": "busy", "message": "렌더 중에는 미리듣기를 새로 만들 수 없습니다."})
    try:
        engine = engines.get("supertonic" if is_st else "vibevoice")
        script = Script(
            title="preview", format="Monologue",
            segments=[{"speaker": "NARRATOR",
                       "text": PREVIEW_TEXT_KO if is_st else PREVIEW_TEXT_EN}],  # type: ignore[list-item]
        )
        result = engine.render(
            script, {"NARRATOR": voice_id},
            on_progress=lambda *a: None, should_cancel=lambda: False,
        )
    except EngineError as exc:
        raise HTTPException(502, detail={"code": exc.code, "message": exc.message}) from exc
    finally:
        GPU_LOCK.release()

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PREVIEW_DIR / f".{safe}.tmp.wav"
    A.write_wav(tmp, result.audio, result.sample_rate)
    try:
        A.encode(tmp, cached, fmt="mp3", bitrate_kbps=128,
                 lufs=settings.loudness_lufs, sample_rate=result.sample_rate)
    finally:
        tmp.unlink(missing_ok=True)
    return FileResponse(str(cached))


# ------------------------------------------------------------ Anki 내보내기


@app.post("/export/anki")
def export_anki(body: dict) -> dict:
    """완성된 렌더를 Anki 덱(.apkg)으로 — 구간 오디오 + 문장 + 번역 카드."""
    import genanki

    audio_path = Path(str(body.get("audio_path") or ""))
    title = str(body.get("title") or audio_path.stem or "VoiceDesk")
    raw_timings = body.get("timings") or []
    out_dir = Path(settings.output_dir).resolve()
    if not audio_path.is_file() or out_dir not in audio_path.resolve().parents:
        raise HTTPException(404, detail={"code": "no_audio", "message": "오디오 파일이 없습니다."})
    if not raw_timings:
        raise HTTPException(400, detail={"code": "no_timings", "message": "구간 정보가 없습니다."})

    import hashlib
    import tempfile

    deck_id = int(hashlib.sha256(title.encode()).hexdigest()[:8], 16) | 1
    model = genanki.Model(
        1706259371,
        "VoiceDesk 문장",
        fields=[{"name": "Audio"}, {"name": "Text"}, {"name": "Translation"}],
        templates=[{
            "name": "듣고 이해하기",
            "qfmt": "{{Audio}}",
            "afmt": "{{FrontSide}}<hr id=answer>{{Text}}<br><span style='color:#888'>{{Translation}}</span>",
        }],
    )
    deck = genanki.Deck(deck_id, f"VoiceDesk::{title}")

    media: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        for t in raw_timings:
            i = int(t["index"])
            start, end = float(t["start"]), float(t["end"])
            if end - start < 0.2:
                continue
            clip = Path(td) / f"voicedesk_{deck_id}_{i:03d}.mp3"
            A.cut_segment(audio_path, clip, start, end)
            media.append(str(clip))
            deck.add_note(genanki.Note(model=model, fields=[
                f"[sound:{clip.name}]",
                str(t.get("text") or ""),
                str(t.get("translation") or ""),
            ]))
        pkg = genanki.Package(deck)
        pkg.media_files = media
        dst = unique_path(audio_path.parent, audio_path.stem, "apkg")
        pkg.write_to_file(str(dst))

    return {"path": str(dst), "cards": len(media)}


# ------------------------------------------------------------ 모델 다운로드


@app.post("/models/download", response_model=JobStatus)
def models_download(body: dict) -> JobStatus:
    from . import downloads

    which = str(body.get("which") or "")
    if which not in downloads.CATALOG:
        raise HTTPException(400, detail={"code": "unknown_model",
                                         "message": f"모르는 모델입니다: {which}"})
    job = jobs.create("download")

    def work(j: Job) -> None:
        j.set_state("running", f"{downloads.CATALOG[which]['label']} 내려받는 중")
        downloads.start(which, j)

    # 다운로드는 GPU 를 안 쓰므로 GPU_LOCK 대기 없이 바로 돈다
    import threading as _th

    def wrapper() -> None:
        from .engines.base import EngineError as _EE

        try:
            job.set_state("running", "시작")
            work(job)
            job.progress = 1.0
            job.set_state("done", "완료")
        except _EE as exc:
            job.error_code, job.error = exc.code, exc.message
            job.set_state("error", exc.message)
        except Exception as exc:  # noqa: BLE001
            job.error_code, job.error = "download", str(exc)[:300]
            job.set_state("error", job.error)

    _th.Thread(target=wrapper, daemon=True).start()
    return job.status()


# ---------------------------------------------------------------- 설정


@app.get("/settings", response_model=Settings)
def get_settings() -> Settings:
    return settings


@app.put("/settings", response_model=Settings)
def put_settings(patch: dict) -> Settings:
    global settings
    data = settings.model_dump() | {k: v for k, v in patch.items() if k in settings.model_dump()}
    new = Settings.model_validate(data)
    new.save()
    settings = new
    engines.refresh_settings(new)
    return settings


@app.post("/settings/gemini-key")
def set_key(body: dict) -> dict:
    key = (body.get("key") or "").strip()
    if not key:
        secrets_store.clear_gemini_key()
        return {"has_key": False}
    secrets_store.set_gemini_key(key)
    return {"has_key": True}


@app.post("/cache/clear")
def clear_cache() -> dict:
    from .engines.dia2_engine import Dia2Engine  # torch 를 여기서만 끌어온다

    return {"removed": Dia2Engine.clear_cache()}


@app.post("/engine/unload")
def unload_engine() -> dict:
    engines.unload()
    return {"loaded": engines.loaded_name}


@app.post("/shutdown")
def shutdown() -> dict:
    """Tauri sidecar 종료 경로. 앱이 닫히면 백엔드도 반드시 함께 죽어야 한다."""
    def stop() -> None:
        engines.unload()
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Timer(0.3, stop).start()
    return {"stopping": True}


def _port_free(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def main() -> None:
    import argparse
    import sys

    import uvicorn

    ap = argparse.ArgumentParser(prog="voicedesk-backend")
    ap.add_argument("--port", type=int, default=None, help="설정값을 덮어쓴다")
    ap.add_argument("--host", default=None)
    args = ap.parse_args()

    host = args.host or settings.host
    port = args.port or settings.port

    if not _port_free(host, port):
        # 이 PC 처럼 WSL 이 7860 을 물고 있는 경우를 위해 빈 포트로 물러난다.
        # --port 로 명시한 경우는 호출자가 그 포트를 기대하므로 물러나지 않는다.
        if args.port is not None:
            log.error(
                "포트 %d 를 이미 다른 프로그램이 쓰고 있습니다. "
                "그 프로그램을 끄거나 설정에서 서버 포트를 바꿔주세요.", port,
            )
            sys.exit(3)
        for cand in range(port + 1, port + 11):
            if _port_free(host, cand):
                log.warning("포트 %d 가 사용 중이라 %d 로 물러납니다.", port, cand)
                port = cand
                settings.port = cand
                settings.save()  # Tauri 쪽이 같은 파일을 읽으므로 여기 기록한다
                break
        else:
            log.error("포트 %d~%d 가 모두 사용 중입니다. 설정에서 포트를 바꿔주세요.",
                      port, port + 10)
            sys.exit(3)

    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
    log.info("VoiceDesk %s — http://%s:%d", VERSION, host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
