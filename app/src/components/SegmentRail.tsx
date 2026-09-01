/**
 * 세그먼트 레일 — 이 앱의 시그니처 (design/DIRECTION.md 6절).
 *
 * 대본 카드 왼쪽에 붙는 세로 레일이 곧 타임라인이다. 칸 하나 = 세그먼트 하나이고,
 * 칸의 높이가 그 세그먼트의 길이에 비례한다. 승인 전에는 예상 길이, 렌더 중에는
 * 합성이 끝난 칸부터 앰버로 점등, 완료 후에는 재생 위치를 표시하는 스크럽 바가 된다.
 *
 * 근거: 이 제품의 본질은 텍스트 구간 -> 시간 구간 매핑이고, 그 매핑이 타임스탬프
 * json 으로 파일에 남는다. 화면에서만 안 보이는 건 이상하다.
 */
import { useMemo } from "react";

import type { Segment, SegmentTiming } from "@/lib/types";
import { cn, wordCount } from "@/lib/utils";

export type RailState = "draft" | "rendering" | "done";

const MIN_ROW = 34; // 32px 격자 + 보더

export function SegmentRail({
  segments,
  timings,
  state,
  renderedCount = 0,
  activeIndex,
  playingIndex,
  onSelect,
  rowHeights,
}: {
  segments: Segment[];
  timings?: SegmentTiming[] | null;
  state: RailState;
  /** 렌더 중 지금까지 합성이 끝난 칸 수 */
  renderedCount?: number;
  activeIndex?: number | null;
  playingIndex?: number | null;
  onSelect?: (index: number) => void;
  /** 카드 실제 높이. 주면 레일이 카드와 정확히 나란히 선다. */
  rowHeights?: number[];
}) {
  const heights = useMemo(() => {
    if (rowHeights && rowHeights.length === segments.length) {
      return rowHeights.map((h) => Math.max(MIN_ROW, h));
    }
    // 카드 높이를 아직 모르면 길이 비례로 그린다.
    const weights = segments.map((s) =>
      timings ? Math.max(0.3, timings[s ? segments.indexOf(s) : 0]?.end ?? 1) : wordCount(s.text) + 2,
    );
    const total = weights.reduce((a, b) => a + b, 0) || 1;
    return weights.map((w) => Math.max(MIN_ROW, (w / total) * 420));
  }, [segments, timings, rowHeights]);

  return (
    <div
      role="list"
      aria-label="세그먼트 타임라인"
      className="flex w-[10px] shrink-0 flex-col gap-[2px]"
    >
      {segments.map((seg, i) => {
        const done = state === "done" || (state === "rendering" && i < renderedCount);
        const busy = state === "rendering" && i === renderedCount;
        const playing = playingIndex === i;
        const active = activeIndex === i;

        return (
          <button
            key={i}
            role="listitem"
            type="button"
            aria-label={`구간 ${i + 1}, ${seg.speaker}${
              playing ? ", 재생 중" : busy ? ", 합성 중" : ""
            }`}
            aria-current={active || undefined}
            onClick={() => onSelect?.(i)}
            style={{ height: heights[i] }}
            className={cn(
              "group relative w-full rounded-[1px] transition-colors duration-[160ms] ease-out",
              // 기본은 꺼져 있다 (Unlit)
              "bg-line-soft",
              done && "bg-lamp-signal/35",
              busy && "bg-lamp-signal lamp-pulse",
              playing && "bg-lamp-signal",
              active && !playing && !busy && "bg-text-3",
              onSelect && "cursor-pointer hover:bg-text-2",
            )}
          />
        );
      })}
    </div>
  );
}

/** 레일 옆에 붙는 타임코드 열. tabular-nums 로 자리가 흔들리지 않는다. */
export function RailTimes({
  timings,
  rowHeights,
}: {
  timings: SegmentTiming[];
  rowHeights?: number[];
}) {
  return (
    <div className="flex w-[52px] shrink-0 flex-col gap-[2px]">
      {timings.map((t, i) => (
        <div
          key={t.index}
          style={{ height: rowHeights?.[i] ?? MIN_ROW }}
          className="t-meter flex items-start pt-1 text-[11px] text-text-3"
        >
          {fmt(t.start)}
        </div>
      ))}
    </div>
  );
}

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
}
