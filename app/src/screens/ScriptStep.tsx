import {
  ArrowDown, ArrowUp, Play, RefreshCw, Trash2, Volume2,
} from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";

import { SegmentRail } from "@/components/SegmentRail";
import { Button, ErrorNote, Legend, Select, Textarea } from "@/components/ui";
import type { EngineName, Script, Segment, SpeakerId, Voice } from "@/lib/types";
import { cn, humanSeconds, speakerLabel, wordCount } from "@/lib/utils";

const ENGINES: { value: EngineName; label: string; hint: string }[] = [
  { value: "vibevoice", label: "VibeVoice", hint: "영어·중국어 · 화자 4명 · 긴 대화" },
  { value: "dia2", label: "Dia2", hint: "영어 · 화자 2명 · 줄 재합성 · 클로닝" },
  { value: "supertonic", label: "Supertonic", hint: "한국어·다국어 · CPU · 매우 빠름" },
];

export function ScriptStep({
  script,
  onChange,
  voices,
  voiceMap,
  onVoiceMap,
  engine,
  onEngine,
  onPreviewSegment,
  onRegenerateSegment,
  onPreviewVoice,
  onRender,
  busySegment,
  error,
  references,
  onPickReference,
}: {
  script: Script;
  onChange: (s: Script) => void;
  voices: Voice[];
  voiceMap: Record<string, string>;
  onVoiceMap: (m: Record<string, string>) => void;
  engine: EngineName;
  onEngine: (e: EngineName) => void;
  onPreviewSegment: (index: number) => void;
  onRegenerateSegment: (index: number) => void;
  onPreviewVoice: (voiceId: string) => void;
  onRender: () => void;
  busySegment: number | null;
  error: string | null;
  /** Dia2 레퍼런스 클로닝: 화자 -> wav 경로 */
  references: Record<string, string>;
  onPickReference: (speaker: string) => void;
}) {
  const [active, setActive] = useState<number | null>(0);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [heights, setHeights] = useState<number[]>([]);

  // 레일 칸이 카드와 정확히 나란히 서도록 실제 높이를 잰다.
  useLayoutEffect(() => {
    const next = rowRefs.current.slice(0, script.segments.length).map((el) => el?.offsetHeight ?? 34);
    setHeights((prev) =>
      prev.length === next.length && prev.every((v, i) => v === next[i]) ? prev : next,
    );
  });

  const speakers = [...new Set(script.segments.map((s) => s.speaker))];
  const words = script.segments.reduce((a, s) => a + wordCount(s.text), 0);
  const estimate = words / 2.5;
  const tooManyForDia2 = engine === "dia2" && speakers.length > 2;
  // 엔진에 맞는 보이스만 보여준다 (Supertonic 스타일 <-> wav 프리셋)
  const engineVoices = voices.filter((v) =>
    engine === "supertonic" ? v.engine === "supertonic" : v.engine !== "supertonic",
  );

  function patch(i: number, p: Partial<Segment>) {
    const segs = script.segments.slice();
    segs[i] = { ...segs[i], ...p };
    onChange({ ...script, segments: segs });
  }
  function remove(i: number) {
    if (script.segments.length <= 1) return;
    const segs = script.segments.slice();
    segs.splice(i, 1);
    onChange({ ...script, segments: segs });
    setActive(Math.max(0, i - 1));
  }
  function move(i: number, delta: number) {
    const j = i + delta;
    if (j < 0 || j >= script.segments.length) return;
    const segs = script.segments.slice();
    [segs[i], segs[j]] = [segs[j], segs[i]];
    onChange({ ...script, segments: segs });
    setActive(j);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 상단 고정 바 — 제목, 엔진, 예상 길이 */}
      <div className="flex shrink-0 items-end gap-4 px-6 pb-4 pt-5">
        <div className="min-w-0 flex-1">
          <Legend>대본 제목</Legend>
          <input
            value={script.title}
            onChange={(e) => onChange({ ...script, title: e.target.value })}
            className="w-full bg-transparent t-display text-text-1 outline-none placeholder:text-text-3"
            placeholder="제목 없음"
          />
        </div>
        <div className="flex shrink-0 items-end gap-4">
          <div className="flex w-[150px] flex-col gap-1.5">
            <Legend>엔진</Legend>
            <Select value={engine} options={ENGINES} onValueChange={onEngine} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Legend>예상 길이</Legend>
            <span className="t-meter pb-1.5 text-text-1">{humanSeconds(estimate)}</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <Legend>구간</Legend>
            <span className="t-meter pb-1.5 text-text-1">{script.segments.length}</span>
          </div>
        </div>
      </div>

      {/* 화자별 보이스 */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-y border-line bg-surface-1 px-6 py-2.5">
        <Legend className="mr-1">VOICES</Legend>
        {speakers.map((sp) => (
          <div key={sp} className="flex items-center gap-1.5">
            <span className="rounded-[--radius-1] border border-line bg-surface-3 px-1.5 py-0.5 t-meter text-[11px] text-text-2">
              {speakerLabel(sp)}
            </span>
            <div className="w-[186px]">
              <Select
                value={engineVoices.some((v) => v.id === voiceMap[sp]) ? voiceMap[sp] : undefined}
                placeholder="보이스 고르기"
                options={engineVoices.map((v) => ({ value: v.id, label: v.label }))}
                onValueChange={(v) => onVoiceMap({ ...voiceMap, [sp]: v })}
              />
            </div>
            <Button
              variant="ghost"
              size="iconSm"
              aria-label={`${speakerLabel(sp)} 보이스 미리듣기`}
              disabled={!voiceMap[sp]}
              onClick={() => voiceMap[sp] && onPreviewVoice(voiceMap[sp])}
            >
              <Volume2 className="size-3.5" />
            </Button>
            {engine === "dia2" ? (
              <button
                type="button"
                title="내 목소리 wav 로 클로닝 (5~30초 녹음)"
                onClick={() => onPickReference(sp)}
                className={cn(
                  "t-meter rounded-[--radius-1] border px-1.5 py-0.5 text-[11px]",
                  "transition-colors duration-[120ms]",
                  references[sp]
                    ? "border-lamp-ready/50 text-lamp-ready"
                    : "border-line text-text-3 hover:text-text-1",
                )}
              >
                {references[sp] ? "클로닝 ✓" : "클로닝"}
              </button>
            ) : null}
          </div>
        ))}
      </div>

      {tooManyForDia2 ? (
        <div className="px-6 pt-4">
          <ErrorNote
            message={`화자가 ${speakers.length}명입니다. Dia2는 2명까지이니 VibeVoice로 바꾸거나 화자를 줄여주세요.`}
            action={
              <Button variant="outline" size="sm" onClick={() => onEngine("vibevoice")}>
                VibeVoice로
              </Button>
            }
          />
        </div>
      ) : null}
      {error ? (
        <div className="px-6 pt-4">
          <ErrorNote message={error} />
        </div>
      ) : null}

      {/* 레일 + 카드 */}
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        <div className="flex gap-3">
          <div className="sticky top-0 pt-px">
            <SegmentRail
              segments={script.segments}
              state="draft"
              activeIndex={active}
              onSelect={setActive}
              rowHeights={heights}
            />
          </div>

          <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
            {script.segments.map((seg, i) => (
              <div
                key={i}
                ref={(el) => {
                  rowRefs.current[i] = el;
                }}
                onFocusCapture={() => setActive(i)}
                onClick={() => setActive(i)}
                className={cn(
                  "group rounded-[--radius-2] border px-3 py-2.5 transition-colors duration-[120ms]",
                  active === i
                    ? "border-line bg-surface-2"
                    : "border-transparent hover:border-line-soft hover:bg-surface-2/60",
                )}
              >
                <div className="flex items-start gap-3">
                  <div className="flex w-[86px] shrink-0 flex-col gap-1.5 pt-0.5">
                    <Select
                      value={seg.speaker}
                      options={(["NARRATOR", "A", "B", "C", "D"] as SpeakerId[]).map((s) => ({
                        value: s,
                        label: speakerLabel(s),
                      }))}
                      onValueChange={(v) => patch(i, { speaker: v })}
                      className="h-7 px-2 text-[12px]"
                    />
                    <span className="t-meter pl-0.5 text-[11px] text-text-3">
                      {wordCount(seg.text)}단어
                    </span>
                  </div>

                  <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <Textarea
                      rows={Math.min(8, Math.max(2, Math.ceil(seg.text.length / 76)))}
                      value={seg.text}
                      onChange={(e) => patch(i, { text: e.target.value })}
                      className="border-transparent bg-transparent px-1 hover:border-line focus:border-line"
                    />
                    <input
                      value={seg.note ?? ""}
                      onChange={(e) => patch(i, { note: e.target.value.trim() || null })}
                      placeholder="연기 메모 (선택) — 음성으로 읽히지 않음 · Dia2는 laughs 같은 태그만 소리로"
                      className={cn(
                        "h-6 w-full bg-transparent px-1 t-meter text-[11px] outline-none",
                        "text-lamp-signal/85 placeholder:text-text-3",
                      )}
                    />
                    {seg.translation != null || script.segments.some((s) => s.translation) ? (
                      <input
                        value={seg.translation ?? ""}
                        onChange={(e) => patch(i, { translation: e.target.value.trim() || null })}
                        placeholder="한국어 번역 (표시·자막용)"
                        className={cn(
                          "h-6 w-full bg-transparent px-1 text-[12px] outline-none",
                          "text-text-2 placeholder:text-text-3",
                        )}
                      />
                    ) : null}
                  </div>

                  <div
                    className={cn(
                      "flex shrink-0 flex-col gap-0.5 opacity-0 transition-opacity duration-[120ms]",
                      "group-hover:opacity-100 group-focus-within:opacity-100",
                      active === i && "opacity-100",
                    )}
                  >
                    <Button
                      variant="ghost"
                      size="iconSm"
                      aria-label="이 줄만 들어보기"
                      disabled={busySegment != null}
                      onClick={() => onPreviewSegment(i)}
                    >
                      <Play className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="iconSm"
                      aria-label="이 줄만 다시 생성"
                      disabled={busySegment != null}
                      onClick={() => onRegenerateSegment(i)}
                    >
                      <RefreshCw className={cn("size-3.5", busySegment === i && "lamp-pulse")} />
                    </Button>
                    <Button variant="ghost" size="iconSm" aria-label="위로" onClick={() => move(i, -1)}>
                      <ArrowUp className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="iconSm" aria-label="아래로" onClick={() => move(i, 1)}>
                      <ArrowDown className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="iconSm"
                      aria-label="삭제"
                      disabled={script.segments.length <= 1}
                      onClick={() => remove(i)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-center pt-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              onChange({
                ...script,
                segments: [
                  ...script.segments,
                  { speaker: script.segments.at(-1)?.speaker ?? "NARRATOR", text: "", note: null },
                ],
              })
            }
          >
            구간 추가
          </Button>
        </div>
      </div>

      <div className="flex shrink-0 items-center justify-end gap-3 border-t border-line px-6 py-3">
        <span className="t-legend">{words} WORDS</span>
        <Button
          disabled={tooManyForDia2 || script.segments.some((s) => !s.text.trim())}
          onClick={onRender}
        >
          음성 만들기
        </Button>
      </div>
    </div>
  );
}
