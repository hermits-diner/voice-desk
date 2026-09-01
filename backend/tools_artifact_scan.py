"""금속성 링잉(협대역 톤 잡음) 흔적 스캔.

쇠소리는 스펙트럼에서 좁은 주파수 대역에 에너지가 몰린 지속 톤으로 나타난다.
말소리가 없는(저에너지) 프레임과 파일 끝부분에서 2~11kHz 대역의
피크/중앙값 비(톤성)와 그 피크 주파수를 잰다.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

FFMPEG = r"C:\ai\voice-desk\backend\bin\ffmpeg.exe"


def load(path: str) -> tuple[np.ndarray, int]:
    p = Path(path)
    if p.suffix.lower() == ".mp3":
        fd, tmp_name = tempfile.mkstemp(suffix=".wav")
        os.close(fd)  # 열린 fd 를 두면 Windows 가 삭제를 막는다
        tmp = Path(tmp_name)
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(p), str(tmp)], check=True, creationflags=0x08000000)
        x, sr = sf.read(str(tmp), dtype="float32", always_2d=True)
        tmp.unlink(missing_ok=True)
    else:
        x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    return x.mean(axis=1), sr


def scan(path: str) -> None:
    x, sr = load(path)
    n_fft, hop = 2048, 512
    win = np.hanning(n_fft)
    frames = []
    for i in range(0, len(x) - n_fft, hop):
        frames.append(np.abs(np.fft.rfft(x[i:i + n_fft] * win)))
    S = np.array(frames)                      # (T, F)
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    t_per_frame = hop / sr

    rms = np.sqrt((np.array([x[i:i + n_fft] ** 2 for i in range(0, len(x) - n_fft, hop)])).mean(axis=1))
    db = 20 * np.log10(rms + 1e-12)

    band = (freqs >= 2000) & (freqs <= 11000)
    fb = freqs[band]

    def tonality(rows: np.ndarray) -> tuple[float, float]:
        """(피크/중앙값 비 dB, 피크 주파수 Hz)"""
        if rows.size == 0:
            return 0.0, 0.0
        spec = rows[:, band].mean(axis=0)
        peak_i = int(np.argmax(spec))
        ratio = 20 * np.log10((spec[peak_i] + 1e-12) / (np.median(spec) + 1e-12))
        return float(ratio), float(fb[peak_i])

    # 1) 말소리 없는 구간 (하위 15% 에너지 프레임)
    quiet = S[db < np.percentile(db, 15)]
    q_ratio, q_freq = tonality(quiet)

    # 2) 마지막 1.5초
    tail_frames = int(1.5 / t_per_frame)
    t_ratio, t_freq = tonality(S[-tail_frames:])

    # 3) 발화 구간 (상위 50%) 의 고역 에너지 비율
    loud = S[db > np.percentile(db, 50)]
    hf = loud[:, freqs >= 8000].mean()
    total = loud.mean()

    name = Path(path).name
    print(f"{name}")
    print(f"  무음부 톤성   : {q_ratio:5.1f} dB  @ {q_freq:6.0f} Hz   (15dB↑면 뚜렷한 톤)")
    print(f"  끝 1.5초 톤성 : {t_ratio:5.1f} dB  @ {t_freq:6.0f} Hz")
    print(f"  발화부 8kHz+  : {100 * hf / total:4.1f} %")
    print()


if __name__ == "__main__":
    for p in sys.argv[1:]:
        scan(p)
