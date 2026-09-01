"""파일 끝 4초를 50ms 단위로 프로파일링: RMS·지배 주파수·톤성."""
import sys
import numpy as np
import soundfile as sf

x, sr = sf.read(sys.argv[1], dtype="float32", always_2d=True)
x = x.mean(axis=1)
win = int(sr * 0.05)
tail = x[-int(sr * 4):]
print(f"{'t(끝기준)':>9} {'RMS dBFS':>9} {'지배Hz':>7} {'톤성dB':>7}")
for i in range(0, len(tail) - win, win):
    seg = tail[i:i + win]
    rms = 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-12)
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs = np.fft.rfftfreq(len(seg), 1 / sr)
    b = freqs >= 300
    pk = int(np.argmax(spec[b]))
    ton = 20 * np.log10((spec[b][pk] + 1e-12) / (np.median(spec[b]) + 1e-12))
    t = -(len(tail) - i) / sr
    print(f"{t:9.2f} {rms:9.1f} {freqs[b][pk]:7.0f} {ton:7.1f}")
