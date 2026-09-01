import { FolderOpen, Layers, Mic, RotateCcw, StepForward } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";

import { SegmentRail } from "@/components/SegmentRail";
import { Waveform } from "@/components/Waveform";
import { Button, Card, ErrorNote, Legend, Readout } from "@/components/ui";
import type { JobStatus, Script, SegmentTiming } from "@/lib/types";
import { cn, humanSeconds, mmss, speakerLabel } from "@/lib/utils";

export function RenderStep({
  script,
  job,
  peaks,
  currentTime,
  duration,
  timings,
  playingIndex,
  loopSegment,
  onSeek,
  onPlaySegment,
  onToggleLoopSegment,
  onOpenFolder,
  onBackToScript,
  onRetry,
  onExportAnki,
  ankiState,
  onNextEpisode,
  onResumeFrom,
  onPractice,
}: {
  script: Script;
  job: JobStatus | null;
  peaks: Float32Array | null;
  currentTime: number;
  duration: number;
  timings: SegmentTiming[] | null;
  playingIndex: number | null;
  loopSegment: number | null;
  onSeek: (s: number) => void;
  onPlaySegment: (i: number) => void;
  onToggleLoopSegment: (i: number) => void;
  onOpenFolder: () => void;
  onBackToScript: () => void;
  onRetry: () => void;
  onExportAnki: () => void;
  ankiState: "idle" | "busy" | "done" | "error";
  onNextEpisode: () => void;
  /** 실험: 이 구간부터만 다시 렌더 (앞부분은 재사용) */
  onResumeFrom: (index: number) => void;
  onPractice: (index: number) => void;
}) {
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [heights, setHeights] = useState<number[]>([]);
  useLayoutEffect(() => {
    const next = rowRefs.current
      .slice(0, script.segments.length)
      .map((el) => el?.offsetHeight ?? 34);
    setHeights((p) => (p.length === next.length && p.every((v, i) => v === next[i]) ? p : next));
  });

  const rendering = job != null && ["queued", "loading", "running", "encoding"].includes(job.state);
  const failed = job?.state === "error";
  const done = job?.state === "done";
  // Dia2 는 구간 번호를 직접 보고한다. VibeVoice 는 대본 전체를 한 번에 렌더하므로
  // 합성된 초(진행률)를 단어 수 비중에 얹어 몇 번째 구간까지 왔는지 추정한다.
  const renderedCount = (() => {
    if (job?.segment_index != null && job.segment_total) return job.segment_index;
    if (!rendering || !job) return 0;
    const weights = script.segments.map((s) => Math.max(1, s.text.split(/\s+/).length));
    const total = weights.reduce((a, b) => a + b, 0);
    let acc = 0;
    let lit = 0;
    for (const w of weights) {
      acc += w / total;
      if (acc <= job.progress) lit += 1;
      else break;
    }
    return lit;
  })();

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-end justify-between gap-4 px-6 pb-4 pt-5">
        <div className="min-w-0">
          <Legend>{done ? "완성" : rendering ? "만드는 중" : "렌더"}</Legend>
          <h1 className="truncate t-display text-text-1">{script.title}</h1>
        </div>
        <div className="flex shrink-0 items-end gap-5">
          <Readout label="LENGTH" value={done ? mmss(duration) : "--:--"} />
          <Readout
            label="ELAPSED"
            value={job ? mmss(job.elapsed) : "--:--"}
            tone={rendering ? "signal" : undefined}
          />
          <Readout
            label="REMAINING"
            value={rendering && job?.eta != null ? humanSeconds(job.eta) : "-"}
          />
        </div>
      </div>

      <div className="shrink-0 px-6">
        <Card className="h-[104px] overflow-hidden p-3">
          <Waveform
            peaks={peaks}
            progress={job?.progress ?? 0}
            currentTime={currentTime}
            duration={duration}
            timings={timings}
            onSeek={done ? onSeek : undefined}
          />
        </Card>
      </div>

      {failed ? (
        <div className="px-6 pt-4">
          <ErrorNote
            message={job?.error ?? "렌더가 실패했습니다."}
            action={
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={onBackToScript}>
                  대본으로
                </Button>
                <Button variant="outline" size="sm" onClick={onRetry}>
                  <RotateCcw className="size-3.5" />
                  다시
                </Button>
              </div>
            }
          />
        </div>
      ) : null}

      {rendering ? (
        <p className="shrink-0 px-6 pt-3 t-body text-text-2">{job?.message}</p>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        <div className="flex gap-3">
          <div className="pt-px">
            <SegmentRail
              segments={script.segments}
              timings={timings}
              state={done ? "done" : rendering ? "rendering" : "draft"}
              renderedCount={renderedCount}
              playingIndex={playingIndex}
              onSelect={done ? onPlaySegment : undefined}
              rowHeights={heights}
            />
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
            {script.segments.map((seg, i) => {
              const t = timings?.[i];
              const isPlaying = playingIndex === i;
              return (
                <div
                  key={i}
                  ref={(el) => {
                    rowRefs.current[i] = el;
                  }}
                  className={cn(
                    "flex items-start gap-3 rounded-[--radius-2] border px-3 py-2",
                    isPlaying ? "border-line bg-surface-2" : "border-transparent",
                  )}
                >
                  <span className="w-[70px] shrink-0 rounded-[--radius-1] border border-line bg-surface-3 px-1.5 py-0.5 text-center t-meter text-[11px] text-text-2">
                    {speakerLabel(seg.speaker)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      data-selectable
                      className={cn("t-body", isPlaying ? "text-text-1" : "text-text-2")}
                    >
                      {seg.text}
                    </p>
                    {seg.translation ? (
                      <p className="text-[12px] leading-5 text-text-3">{seg.translation}</p>
                    ) : null}
                  </div>
                  {t ? (
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        type="button"
                        onClick={() => done && onPlaySegment(i)}
                        disabled={!done}
                        className="t-meter text-[11px] text-text-3 hover:text-text-1 disabled:hover:text-text-3"
                      >
                        {mmss(t.start)} – {mmss(t.end)}
                      </button>
                      <button
                        type="button"
                        aria-label="이 구간 반복"
                        aria-pressed={loopSegment === i}
                        disabled={!done}
                        onClick={() => onToggleLoopSegment(i)}
                        className={cn(
                          "rounded-[--radius-1] px-1.5 py-0.5 t-legend transition-colors duration-[120ms]",
                          loopSegment === i
                            ? "bg-surface-3 text-lamp-signal"
                            : "text-text-3 hover:bg-surface-2 hover:text-text-2",
                        )}
                      >
                        LOOP
                      </button>
                      <button
                        type="button"
                        aria-label="이 구간 발음 연습"
                        disabled={!done}
                        onClick={() => onPractice(i)}
                        title="듣고 따라 말하기"
                        className="rounded-[--radius-1] p-1 text-text-3 transition-colors duration-[120ms] hover:bg-surface-2 hover:text-text-1"
                      >
                        <Mic className="size-3.5" />
                      </button>
                      {done && i > 0 ? (
                        <button
                          type="button"
                          aria-label="이 구간부터 다시 렌더 (실험)"
                          onClick={() => onResumeFrom(i)}
                          title="여기부터 다시 렌더 — 앞부분은 재사용 (실험 기능, 이음새 톤이 튈 수 있음)"
                          className="rounded-[--radius-1] p-1 text-text-3 transition-colors duration-[120ms] hover:bg-surface-2 hover:text-text-1"
                        >
                          <StepForward className="size-3.5" />
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {done ? (
        <div className="flex shrink-0 items-center gap-2 border-t border-line px-6 py-3">
          <span className="min-w-0 flex-1 truncate t-meter text-[11px] text-text-3">
            {job?.audio_path}
          </span>
          <Button variant="ghost" onClick={onNextEpisode} title="같은 인물·설정으로 이어지는 다음 화 대본 만들기">
            다음 화
          </Button>
          <Button
            variant="ghost"
            onClick={onExportAnki}
            disabled={ankiState === "busy"}
            title="구간 오디오 + 문장 + 번역으로 Anki 덱(.apkg) 만들기"
          >
            <Layers className="size-3.5" />
            {ankiState === "busy" ? "만드는 중" : ankiState === "done" ? "Anki 완료" : "Anki"}
          </Button>
          <Button variant="ghost" onClick={onBackToScript}>
            대본 고치기
          </Button>
          <Button onClick={onOpenFolder}>
            <FolderOpen className="size-3.5" />
            폴더 열기
          </Button>
        </div>
      ) : null}
    </div>
  );
}
