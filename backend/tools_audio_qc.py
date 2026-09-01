"""생성된 wav 의 기본 건전성 점검: 무음/클리핑/NaN/구간별 RMS."""
import sys
import numpy as np
import soundfile as sf

path = sys.argv[1]
x, sr = sf.read(path, dtype="float32", always_2d=True)
x = x.mean(axis=1)
print(f"file        : {path}")
print(f"samplerate  : {sr} Hz")
print(f"duration    : {len(x)/sr:.2f} s")
print(f"peak        : {np.abs(x).max():.4f}")
print(f"rms         : {np.sqrt((x**2).mean()):.4f}  ({20*np.log10(np.sqrt((x**2).mean())+1e-12):.1f} dBFS)")
print(f"NaN/Inf     : {np.isnan(x).any()} / {np.isinf(x).any()}")
print(f"clipped(>.99): {(np.abs(x) > 0.99).sum()} samples")
dc = x.mean()
print(f"DC offset   : {dc:+.5f}")

win = int(sr * 1.0)
rms = np.array([np.sqrt((x[i:i+win]**2).mean()) for i in range(0, len(x)-win, win)])
db = 20*np.log10(rms + 1e-12)
silent = (db < -50).sum()
print(f"\n초당 RMS(dBFS) — 무음(<-50dB) {silent}/{len(db)} 구간")
bars = "".join("▁▂▃▄▅▆▇█"[min(7, max(0, int((d + 60) / 7.5)))] for d in db)
print(bars)
