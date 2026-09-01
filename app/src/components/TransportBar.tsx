/**
 * 트랜스포트 바 — 하드웨어의 마스터 섹션.
 *
 * 3단계 내내 자리가 바뀌지 않는다. 대기 중엔 엔진과 VRAM 만, 렌더 중엔 진행률,
 * 완료 후엔 재생 컨트롤. 위치가 안 변하는 것이 "장비" 감각의 핵심이다.
 */
import { Headphones, Pause, Play, Repeat, Square } from "lucide-react";

import type { Health, JobStatus, SegmentTiming } from "@/lib/types";
import { cn, humanSeconds, mmss } from "@/lib/utils";
import { Button, Lamp, Legend } from "./ui";

const ENGINE_LABEL: Record<string, string> = {
  vibevoice: "VibeVoice 1.5B",
  dia2: "Dia2 2B",
  supertonic: "Supertonic 3",
};

// 쉐도잉 연습을 생각한 순서: 원속 -> 느리게 -> 더 느리게 -> 빠르게
const SPEEDS = [1, 0.75, 0.5, 1.25, 1.5];

export function TransportBar({
  health,
  job,
  playing,
  currentTime,
  duration,
  timings,
  loopSegment,
  speed,
  live,
  onTogglePlay,
  onSeek,
  onToggleLoop,
  onCancel,
  onSpeed,
  onToggleLive,
}: {
  health: Health | null;
  job: JobStatus | null;
  playing: boolean;
  currentTime: number;
  duration: number;
  timings: SegmentTiming[] | null;
  loopSegment: number | null;
  speed: number;
  live: boolean;
  onTogglePlay: () => void;
  onSeek: (seconds: number) => void;
  onToggleLoop: () => void;
  onCancel: () => void;
  onSpeed: (v: number) => void;
  onToggleLive: () => void;
}) {
  const rendering =
    job != null && ["queued", "loading", "running", "encoding"].includes(job.state);
  const ready = job?.state === "done" && duration > 0;

  const lamp = rendering ? "signal" : ready ? "ready" : health?.cuda ? "off" : "clip";
  const lampLabel = rendering
    ? job?.state === "loading" ? "LOADING" : "RENDERING"
    : ready ? "READY"
    : health?.cuda ? "IDLE" : "NO GPU";

  return (
    <footer className="flex h-11 shrink-0 items-center gap-4 border-t border-line bg-chrome px-3">
      <Lamp tone={lamp as never} pulse={rendering} label={lampLabel} />

      {rendering ? (
        <>
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <div className="h-[2px] flex-1 overflow-hidden bg-line">
              <div
                className="h-full bg-lamp-signal transition-[width] duration-200 ease-out"
                style={{ width: `${Math.round(job!.progress * 100)}%` }}
              />
            </div>
            <span className="t-meter shrink-0 text-text-2">
              {Math.round(job!.progress * 100)}%
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-4">
            <Meter label="ELAPSED" value={mmss(job!.elapsed)} />
            <Meter
              label="REMAINING"
              value={job!.eta != null ? humanSeconds(job!.eta) : "-"}
            />
            {job!.segment_total ? (
              <Meter
                label="SEGMENT"
                value={`${job!.segment_index ?? 0}/${job!.segment_total}`}
              />
            ) : null}
          </div>
          <Button
            variant={live ? "primary" : "ghost"}
            size="sm"
            onClick={onToggleLive}
            aria-pressed={live}
            className="shrink-0"
            title="합성이 끝난 부분부터 이어서 듣기"
          >
            <Headphones className={cn("size-3.5", live && "text-lamp-signal")} />
            이어 듣기
          </Button>
          <Button variant="ghost" size="sm" onClick={onCancel} className="shrink-0">
            <Square className="size-3" />
            중지
          </Button>
        </>
      ) : ready ? (
        <>
          <Button
            variant="outline"
            size="icon"
            onClick={onTogglePlay}
            aria-label={playing ? "정지" : "재생"}
            className="shrink-0"
          >
            {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          </Button>
          <Scrubber
            currentTime={currentTime}
            duration={duration}
            timings={timings}
            onSeek={onSeek}
          />
          <span className="t-meter shrink-0 text-text-1">
            {mmss(currentTime)} <span className="text-text-3">/ {mmss(duration)}</span>
          </span>
          <button
            type="button"
            aria-label={`재생 속도 ${speed}배. 눌러서 바꾸기`}
            title="재생 속도 (쉐도잉용)"
            onClick={() => {
              const i = SPEEDS.indexOf(speed);
              onSpeed(SPEEDS[(i + 1) % SPEEDS.length] ?? 1);
            }}
            className={cn(
              "t-meter shrink-0 rounded-[--radius-1] border px-1.5 py-0.5 text-[11px]",
              "transition-colors duration-[120ms]",
              speed !== 1
                ? "border-text-3 text-text-1"
                : "border-line text-text-3 hover:text-text-1",
            )}
          >
            {speed.toFixed(2).replace(/0$/, "")}×
          </button>
          <Button
            variant={loopSegment != null ? "primary" : "ghost"}
            size="iconSm"
            onClick={onToggleLoop}
            aria-label="구간 반복"
            aria-pressed={loopSegment != null}
            className="shrink-0"
          >
            <Repeat className={cn("size-3.5", loopSegment != null && "text-lamp-signal")} />
          </Button>
        </>
      ) : (
        <div className="flex-1" />
      )}

      <div className="flex shrink-0 items-center gap-4 border-l border-line pl-4">
        <Meter label="ENGINE" value={ENGINE_LABEL[health?.engine ?? ""] ?? "-"} />
        <Meter
          label="VRAM"
          value={
            health?.vram_used_gb != null
              ? `${health.vram_used_gb.toFixed(1)} GB`
              : "-"
          }
        />
      </div>
    </footer>
  );
}

function Meter({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-[3px]">
      <Legend>{label}</Legend>
      <span className="t-meter leading-none text-text-1">{value}</span>
    </div>
  );
}

/** 세그먼트 경계 마커가 찍힌 스크럽 바. */
function Scrubber({
  currentTime,
  duration,
  timings,
  onSeek,
}: {
  currentTime: number;
  duration: number;
  timings: SegmentTiming[] | null;
  onSeek: (s: number) => void;
}) {
  const pct = duration > 0 ? (currentTime / duration) * 100 : 0;
  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label="재생 위치"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(currentTime)}
      aria-valuetext={mmss(currentTime)}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") onSeek(Math.min(duration, currentTime + 5));
        if (e.key === "ArrowLeft") onSeek(Math.max(0, currentTime - 5));
      }}
      onPointerDown={(e) => {
        const el = e.currentTarget;
        const move = (ev: PointerEvent | React.PointerEvent) => {
          const r = el.getBoundingClientRect();
          const x = Math.min(Math.max(0, (ev as PointerEvent).clientX - r.left), r.width);
          onSeek((x / r.width) * duration);
        };
        move(e);
        const up = () => {
          window.removeEventListener("pointermove", move as never);
          window.removeEventListener("pointerup", up);
        };
        window.addEventListener("pointermove", move as never);
        window.addEventListener("pointerup", up);
      }}
      className="relative h-6 min-w-0 flex-1 cursor-pointer"
    >
      <div className="absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 bg-line" />
      <div
        className="absolute left-0 top-1/2 h-[2px] -translate-y-1/2 bg-lamp-signal"
        style={{ width: `${pct}%` }}
      />
      {/* 세그먼트 경계 마커 */}
      {timings?.slice(0, -1).map((t) => (
        <div
          key={t.index}
          className="absolute top-1/2 h-[7px] w-px -translate-y-1/2 bg-text-3"
          style={{ left: `${(t.end / duration) * 100}%` }}
        />
      ))}
      <div
        className="absolute top-1/2 size-[9px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-lamp-signal"
        style={{ left: `${pct}%` }}
      />
    </div>
  );
}
