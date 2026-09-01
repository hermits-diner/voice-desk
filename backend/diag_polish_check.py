"""polish() 전후 비교: 금속 프레임 수 · 발화 구간 보존 여부."""
import sys
import numpy as np
import soundfile as sf

sys.path.insert(0, r"C:\ai\voice-desk\backend")
from app.audio import polish
from diag_metallic import metallic_score

for name in ["diag_metal_10_Alice.wav", "diag_metal_20_Maya.wav"]:
    path = rf"C:\ai\voice-desk\backend\outputs\{name}"
    x, sr = sf.read(path, dtype="float32", always_2d=False)
    before, total_b, _ = metallic_score(x, sr)
    y, notes = polish(x, sr)
    after, total_a, _ = metallic_score(y, sr)

    # 발화 구간(에너지 상위 50% 20ms 프레임)이 훼손되지 않았는지: 겹치는 길이에서 비교
    n = min(len(x), len(y))
    f = int(sr * 0.02)
    k = n // f
    xr = x[:k*f].reshape(k, f); yr = y[:k*f].reshape(k, f)
    rms_x = np.sqrt((xr**2).mean(axis=1))
    loud = rms_x > np.percentile(rms_x, 50)
    diff = np.abs(xr[loud] - yr[loud]).max()
    print(f"{name}")
    print(f"  금속 프레임 {before}/{total_b} -> {after}/{total_a}")
    print(f"  길이 {len(x)/sr:.2f}s -> {len(y)/sr:.2f}s")
    print(f"  발화 프레임 최대 변화: {diff:.6f}  ({'보존' if diff < 0.01 else '변형 있음'})")
    print(f"  notes: {notes}")
    sf.write(path.replace(".wav", "_polished.wav"), y, sr, subtype="PCM_16")
    print()
