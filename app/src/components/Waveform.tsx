/**
 * 파형.
 *
 * 렌더 중에는 아직 파형이 없다. 없는 진폭을 지어내지 않고, 완료된 구간만
 * 앰버 띠로 채워 오른쪽으로 자라게 한다. 렌더가 끝나면 실제 오디오를 디코드해
 * 진짜 피크를 그린다.
 */
import { useEffect, useRef, useState } from "react";

import type { SegmentTiming } from "@/lib/types";

export async function loadPeaks(url: string, buckets = 900): Promise<Float32Array> {
  const res = await fetch(url);
  const buf = await res.arrayBuffer();
  const ctx = new (window.AudioContext || (window as never as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
  try {
    const audio = await ctx.decodeAudioData(buf);
    const ch = audio.getChannelData(0);
    const size = Math.floor(ch.length / buckets) || 1;
    const out = new Float32Array(buckets);
    for (let i = 0; i < buckets; i++) {
      let peak = 0;
      const start = i * size;
      for (let j = 0; j < size && start + j < ch.length; j++) {
        const v = Math.abs(ch[start + j]);
        if (v > peak) peak = v;
      }
      out[i] = peak;
    }
    const max = out.reduce((a, b) => Math.max(a, b), 0) || 1;
    for (let i = 0; i < buckets; i++) out[i] /= max;
    return out;
  } finally {
    void ctx.close();
  }
}

export function Waveform({
  peaks,
  progress,
  currentTime,
  duration,
  timings,
  onSeek,
}: {
  peaks: Float32Array | null;
  /** 렌더 중 진행률 0~1. peaks 가 없을 때만 쓴다. */
  progress?: number;
  currentTime?: number;
  duration?: number;
  timings?: SegmentTiming[] | null;
  onSeek?: (seconds: number) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const el = ref.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      setSize({ w: e.contentRect.width, h: e.contentRect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const cv = ref.current;
    if (!cv || size.w === 0) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = size.w * dpr;
    cv.height = size.h * dpr;
    const g = cv.getContext("2d");
    if (!g) return;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, size.w, size.h);

    const css = getComputedStyle(document.documentElement);
    const signal = css.getPropertyValue("--color-lamp-signal").trim() || "#e2a356";
    const line = css.getPropertyValue("--color-line").trim() || "#38342f";
    const soft = css.getPropertyValue("--color-line-soft").trim() || "#26231f";

    const mid = size.h / 2;
    const playedX =
      duration && currentTime != null && duration > 0
        ? (currentTime / duration) * size.w
        : peaks
          ? 0
          : (progress ?? 0) * size.w;

    if (!peaks) {
      // 렌더 중 — 완료된 만큼만 띠로 채운다. 가짜 진폭을 그리지 않는다.
      g.fillStyle = soft;
      g.fillRect(0, mid - 1, size.w, 2);
      g.fillStyle = signal;
      g.fillRect(0, mid - 9, playedX, 18);
      return;
    }

    const barW = 2;
    const gap = 1;
    const count = Math.floor(size.w / (barW + gap));
    for (let i = 0; i < count; i++) {
      const p = peaks[Math.floor((i / count) * peaks.length)] ?? 0;
      const h = Math.max(1.5, p * (size.h - 8));
      const x = i * (barW + gap);
      g.fillStyle = x <= playedX ? signal : line;
      g.fillRect(x, mid - h / 2, barW, h);
    }

    // 세그먼트 경계 마커
    if (timings && duration) {
      g.fillStyle = css.getPropertyValue("--color-text-3").trim() || "#6f6a63";
      for (const t of timings.slice(0, -1)) {
        const x = (t.end / duration) * size.w;
        g.fillRect(x, 2, 1, size.h - 4);
      }
    }
  }, [peaks, progress, currentTime, duration, timings, size]);

  return (
    <div
      className="relative h-full w-full"
      onPointerDown={
        onSeek && duration
          ? (e) => {
              const r = e.currentTarget.getBoundingClientRect();
              onSeek(((e.clientX - r.left) / r.width) * duration);
            }
          : undefined
      }
      style={{ cursor: onSeek ? "pointer" : "default" }}
    >
      <canvas ref={ref} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}
