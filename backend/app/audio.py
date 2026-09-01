"""오디오 후처리 — 이어붙이기, 라우드니스 정규화, mp3 인코딩, 품질 점검.

ffmpeg 는 동봉한 정적 바이너리만 쓴다 (PATH 를 신뢰하지 않는다).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import FFMPEG, FFPROBE

# 창을 띄우지 않는다 (Tauri sidecar 아래에서 콘솔이 깜빡이는 것 방지)
_NO_WINDOW = 0x08000000


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8",
        errors="replace", creationflags=_NO_WINDOW,
    )


@dataclass
class AudioQc:
    peak: float
    rms_dbfs: float
    clipped_samples: int
    has_nan: bool
    duration: float

    @property
    def degenerate(self) -> bool:
        """발산한 출력인가.

        Dia2 는 샘플링이라 가끔 클리핑된 굉음을 낸다. 실제 관측값:
        정상 -18 ~ -30 dBFS · 클리핑 0, 발산 -6.3 dBFS · 클리핑 27,693.
        """
        if self.has_nan:
            return True
        if self.clipped_samples > 100:
            return True
        if self.rms_dbfs > -10.0:
            return True
        return False


def inspect(path: Path) -> AudioQc:
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if x.size == 0:
        return AudioQc(0.0, -120.0, 0, False, 0.0)
    rms = float(np.sqrt((x ** 2).mean()))
    return AudioQc(
        peak=float(np.abs(x).max()),
        rms_dbfs=float(20 * np.log10(rms + 1e-12)),
        clipped_samples=int((np.abs(x) > 0.99).sum()),
        has_nan=bool(np.isnan(x).any() or np.isinf(x).any()),
        duration=len(x) / sr,
    )


def inspect_array(x: np.ndarray, sr: int) -> AudioQc:
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if x.size == 0:
        return AudioQc(0.0, -120.0, 0, False, 0.0)
    rms = float(np.sqrt((x ** 2).mean()))
    return AudioQc(
        peak=float(np.abs(x).max()),
        rms_dbfs=float(20 * np.log10(rms + 1e-12)),
        clipped_samples=int((np.abs(x) > 0.99).sum()),
        has_nan=bool(np.isnan(x).any() or np.isinf(x).any()),
        duration=len(x) / sr,
    )


def concat_with_gaps(
    chunks: list[np.ndarray],
    sr: int,
    gap_ms: list[int],
) -> np.ndarray:
    """세그먼트 사이에 무음을 넣어 이어붙인다. gap_ms[i] 는 i번과 i+1번 사이."""
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    parts: list[np.ndarray] = []
    for i, c in enumerate(chunks):
        parts.append(np.asarray(c, dtype=np.float32).reshape(-1))
        if i < len(chunks) - 1:
            n = int(sr * gap_ms[i] / 1000) if i < len(gap_ms) else 0
            if n > 0:
                parts.append(np.zeros(n, dtype=np.float32))
    return np.concatenate(parts)


def polish(x: np.ndarray, sr: int) -> tuple[np.ndarray, list[str]]:
    """VibeVoice 출력의 꼬리를 정리한다: 마지막 발화 뒤 잔향 트림 + 페이드아웃.

    구절 사이에 따라붙는 금속성 잔향(-33~-45dBFS 의 1.8~9kHz 톤)은 여기가
    아니라 인코딩 단계의 다운워드 익스팬더(encode 의 expand_quiet)가 줄인다.
    STFT 로 톤만 도려내는 방식도 시도했지만 지표 개선 없이 발화 프레임을
    훼손해서 접었다 (SETUP.md 5-14).
    """
    notes: list[str] = []
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if x.size < sr // 2:
        return x, notes
    y = x.copy()  # 페이드가 호출자 배열을 건드리지 않게

    # ---- 꼬리 트림 + 페이드아웃 ------------------------------------------
    frame = int(sr * 0.02)
    n = len(y) // frame
    rms = np.sqrt((y[: n * frame].reshape(n, frame) ** 2).mean(axis=1))
    db = 20 * np.log10(rms + 1e-12)
    floor = np.percentile(db, 10)
    speech = np.where(db > max(floor + 12.0, -46.0))[0]
    if speech.size:
        end = min(len(y), (speech[-1] + 1) * frame + int(sr * 0.25))
        cut = len(y) - end
        if cut > int(sr * 0.15):
            notes.append(f"끝의 잔향 {cut / sr:.1f}초를 잘라냈습니다.")
        y = y[:end]
    fade = min(int(sr * 0.08), len(y))
    if fade > 0:
        y[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)

    return y, notes


def write_wav(path: Path, x: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(x, dtype=np.float32).reshape(-1), sr, subtype="PCM_16")


def measure_loudness(src: Path, pre_filter: str | None = None) -> dict[str, str] | None:
    """loudnorm 1패스 측정. 실패하면 None 을 돌려 단일 패스로 폴백한다.

    pre_filter 가 있으면 그 필터를 거친 뒤의 소리를 측정한다 — 2패스째와
    같은 체인으로 재야 측정값이 맞는다.
    """
    chain = "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json"
    if pre_filter:
        chain = f"{pre_filter},{chain}"
    p = _run([
        str(FFMPEG), "-hide_banner", "-nostats", "-i", str(src),
        "-af", chain,
        "-f", "null", "-",
    ])
    blob = p.stderr or ""
    start, end = blob.rfind("{"), blob.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(blob[start:end + 1])
    except json.JSONDecodeError:
        return None


# 다운워드 익스팬더 — 발화(-30dBFS 이상)는 건드리지 않고, 구절 사이에
# 따라붙는 금속성 잔향(-35~-45dBFS)을 4~13dB 낮춘다. loudnorm 의 +9dB 게인이
# 이 잔향을 들리게 만들었으므로, 게인 전에 눌러 둔다.
#   입력 -30dB 이상: 그대로 / -42dB -> -52dB / 그 아래는 1.4:1 로 더 깊게
_EXPANDER = (
    "compand=attacks=0.004:decays=0.12:"
    "points=-90/-120|-42/-52|-30/-30|0/0:soft-knee=3:delay=0.004"
)


def encode(
    src_wav: Path,
    dst: Path,
    *,
    fmt: str = "mp3",
    bitrate_kbps: int = 128,
    lufs: float = -16.0,
    sample_rate: int = 24000,
    expand_quiet: bool = False,
) -> None:
    """(선택) 익스팬더 -> 2패스 loudnorm -> 인코딩.

    loudnorm 은 내부적으로 192kHz 로 올렸다가 출력하므로 -ar 로 원래
    샘플레이트를 명시하지 않으면 24kHz 소스가 48kHz 로 나와 비트레이트만 낭비한다.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    m = measure_loudness(src_wav, pre_filter=_EXPANDER if expand_quiet else None)
    if m:
        af = (
            f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
            f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
            f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
            f":offset={m['target_offset']}:linear=true"
        )
    else:
        af = f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
    if expand_quiet:
        af = f"{_EXPANDER},{af}"

    args = [
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src_wav), "-af", af, "-ar", str(sample_rate),
    ]
    if fmt == "mp3":
        args += ["-c:a", "libmp3lame", "-b:a", f"{bitrate_kbps}k"]
    else:
        args += ["-c:a", "pcm_s16le"]
    args.append(str(dst))

    p = _run(args)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg 인코딩 실패: {(p.stderr or '').strip()[:400]}")


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(path: Path, timings) -> None:  # noqa: ANN001
    """세그먼트 타이밍 -> SRT. 번역이 있으면 둘째 줄로 넣는다 (학습용 관례)."""
    blocks: list[str] = []
    for i, t in enumerate(timings, 1):
        lines = [t.text]
        if getattr(t, "translation", None):
            lines.append(t.translation)
        blocks.append(f"{i}\n{_srt_time(t.start)} --> {_srt_time(t.end)}\n" + "\n".join(lines))
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8-sig")  # 플레이어 호환용 BOM


def write_vtt(path: Path, timings) -> None:  # noqa: ANN001
    blocks: list[str] = ["WEBVTT"]
    for t in timings:
        lines = [t.text]
        if getattr(t, "translation", None):
            lines.append(t.translation)
        blocks.append(
            f"{_srt_time(t.start).replace(',', '.')} --> {_srt_time(t.end).replace(',', '.')}\n"
            + "\n".join(lines)
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def cut_segment(src: Path, dst: Path, start: float, end: float) -> None:
    """구간 mp3 잘라내기 (Anki 카드용). 프레임 정확도를 위해 재인코딩한다."""
    p = _run([
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, start):.3f}", "-to", f"{end:.3f}", "-i", str(src),
        "-c:a", "libmp3lame", "-b:a", "128k", str(dst),
    ])
    if p.returncode != 0:
        raise RuntimeError(f"구간 잘라내기 실패: {(p.stderr or '').strip()[:200]}")


def probe_duration(path: Path) -> float:
    p = _run([
        str(FFPROBE), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    try:
        return float((p.stdout or "0").strip())
    except ValueError:
        return 0.0


def load_audio(path: Path, sr: int) -> np.ndarray:
    """mp3/wav -> float32 모노 PCM (부분 재렌더의 앞부분 재사용에 쓴다)."""
    import os
    import tempfile

    fd, tmp_name = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        p = _run([
            str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(path), "-ac", "1", "-ar", str(sr), str(tmp),
        ])
        if p.returncode != 0:
            raise RuntimeError(f"오디오를 읽지 못했습니다: {(p.stderr or '').strip()[:200]}")
        x, _ = sf.read(str(tmp), dtype="float32", always_2d=False)
        return np.asarray(x, dtype=np.float32).reshape(-1)
    finally:
        tmp.unlink(missing_ok=True)


def crossfade_concat(head: np.ndarray, tail: np.ndarray, sr: int, ms: int = 30) -> np.ndarray:
    """이음새 클릭을 막는 짧은 크로스페이드 연결."""
    n = min(int(sr * ms / 1000), len(head), len(tail))
    if n <= 0:
        return np.concatenate([head, tail])
    fade = np.linspace(0.0, 1.0, n, dtype=np.float32)
    mixed = head[-n:] * (1 - fade) + tail[:n] * fade
    return np.concatenate([head[:-n], mixed, tail[n:]])


def ffmpeg_available() -> bool:
    if not FFMPEG.exists():
        return False
    return _run([str(FFMPEG), "-version"]).returncode == 0
