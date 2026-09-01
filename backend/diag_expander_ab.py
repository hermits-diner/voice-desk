"""익스팬더 A/B: 기존 체인(loudnorm만) vs 새 체인(expander+loudnorm)."""
import subprocess, sys
from pathlib import Path
import numpy as np
import soundfile as sf

sys.path.insert(0, r"C:\ai\voice-desk\backend")
from app.audio import encode, polish, write_wav
from diag_metallic import metallic_score

SRC = Path(r"C:\ai\voice-desk\backend\outputs\diag_metal_10_Alice.wav")
OUTD = Path(r"C:\Users\오정훈\Music\VoiceDesk")
FF = r"C:\ai\voice-desk\backend\bin\ffmpeg.exe"

# polish(꼬리 트림+페이드)는 두 쪽 모두 적용해 익스팬더 효과만 비교한다
x, sr = sf.read(str(SRC), dtype="float32", always_2d=False)
y, notes = polish(x, sr)
print("polish notes:", notes)
tmp = Path(r"C:\ai\voice-desk\backend\outputs\_ab_src.wav")
write_wav(tmp, y, sr)

a = OUTD / "쇠소리AB_1_기존.mp3"
b = OUTD / "쇠소리AB_2_익스팬더.mp3"
encode(tmp, a, expand_quiet=False)
encode(tmp, b, expand_quiet=True)

def stats(p: Path):
    w = Path(str(p) + ".wav")
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p), str(w)],
                   check=True, creationflags=0x08000000)
    z, zsr = sf.read(str(w), dtype="float32", always_2d=True)
    z = z.mean(axis=1)
    w.unlink()
    hits, total, _ = metallic_score(z, zsr)
    f = int(zsr * 0.05)
    k = len(z) // f
    rms = np.sqrt((z[:k*f].reshape(k, f) ** 2).mean(axis=1))
    db = 20 * np.log10(rms + 1e-12)
    quiet = db[db < np.percentile(db, 15)].mean()
    loud = db[db > np.percentile(db, 60)].mean()
    return hits, total, quiet, loud

for label, p in (("기존(loudnorm만)   ", a), ("익스팬더+loudnorm ", b)):
    hits, total, quiet, loud = stats(p)
    print(f"{label} 금속프레임 {hits:3d}/{total}  조용한구간 평균 {quiet:6.1f} dBFS  발화 평균 {loud:6.1f} dBFS")
print()
print("파일:", a, "/", b.name)
