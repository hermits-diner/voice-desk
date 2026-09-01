import { CornerDownLeft } from "lucide-react";
import { useState } from "react";

import { Button, Card, ErrorNote, Field, Input, Legend, Select, Textarea } from "@/components/ui";
import type { Cefr, LengthPreset, ScriptFormat, ScriptRequest } from "@/lib/types";
import { cn } from "@/lib/utils";

const FORMATS: { value: ScriptFormat; label: string; hint: string }[] = [
  { value: "Conversation", label: "대화", hint: "여러 화자가 주고받는 형식" },
  { value: "Narration", label: "나레이션", hint: "한 사람이 설명하듯 읽는 형식" },
  { value: "Interview", label: "인터뷰", hint: "묻고 답하는 형식" },
  { value: "Monologue", label: "독백", hint: "한 사람의 긴 발화" },
];

const LENGTHS: { value: LengthPreset; label: string; hint: string }[] = [
  { value: "short", label: "짧게", hint: "약 180단어 · 1분 남짓" },
  { value: "medium", label: "보통", hint: "약 420단어 · 3분 정도" },
  { value: "long", label: "길게", hint: "약 900단어 · 6분 정도" },
];

const LEVELS: { value: Cefr; label: string; hint: string }[] = [
  { value: "A2", label: "A2", hint: "기초. 짧은 문장과 일상 어휘" },
  { value: "B1", label: "B1", hint: "중급 하. 익숙한 주제를 무리 없이" },
  { value: "B2", label: "B2", hint: "중급 상. 추상적인 주제도 다룸" },
  { value: "C1", label: "C1", hint: "고급. 관용 표현과 긴 문장" },
];

export function TopicStep({
  value,
  onChange,
  onGenerate,
  busy,
  error,
  rawFallback,
  onUseRaw,
  hasKey,
  onOpenSettings,
}: {
  value: ScriptRequest;
  onChange: (v: ScriptRequest) => void;
  onGenerate: () => void;
  busy: boolean;
  error: string | null;
  rawFallback: string | null;
  onUseRaw: (text: string) => void;
  hasKey: boolean;
  onOpenSettings: () => void;
}) {
  const [raw, setRaw] = useState("");
  const multiSpeaker = value.format === "Conversation" || value.format === "Interview";
  const canGo = value.topic.trim().length > 0 && !busy && hasKey;

  return (
    <div className="mx-auto flex w-full max-w-[720px] flex-col gap-6 px-6 py-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="t-display text-text-1">무엇을 만들까요</h1>
        <p className="t-body text-text-2">
          주제와 형식을 정하면 대본을 쓰고, 검토한 뒤 음성으로 만듭니다.
        </p>
      </div>

      {!hasKey ? (
        <ErrorNote
          message="Gemini 키가 없어 대본을 만들 수 없습니다. 설정에서 키를 등록해주세요."
          action={
            <Button variant="outline" size="sm" onClick={onOpenSettings}>
              설정 열기
            </Button>
          }
        />
      ) : null}

      <Card className="flex flex-col gap-5 p-4">
        <Field label="주제 또는 상황" hint="Ctrl+Enter 로 바로 만들 수 있습니다.">
          <Textarea
            autoFocus
            rows={4}
            value={value.topic}
            placeholder="예) 카페에서 처음 만난 두 사람이 각자 좋아하는 여행지를 이야기한다"
            onChange={(e) => onChange({ ...value, topic: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && canGo) {
                e.preventDefault();
                onGenerate();
              }
            }}
          />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="형식">
            <Select
              value={value.format}
              options={FORMATS}
              onValueChange={(v) =>
                onChange({
                  ...value,
                  format: v,
                  speakers: v === "Narration" || v === "Monologue" ? 1 : Math.max(2, value.speakers),
                })
              }
            />
          </Field>

          <Field label="화자 수">
            <div className="flex h-8 items-center gap-1">
              {[1, 2, 3, 4].map((n) => {
                const disabled = !multiSpeaker && n !== 1;
                return (
                  <button
                    key={n}
                    type="button"
                    disabled={disabled}
                    aria-pressed={value.speakers === n}
                    onClick={() => onChange({ ...value, speakers: n })}
                    className={cn(
                      "h-8 flex-1 rounded-[--radius-1] border t-meter transition-colors duration-[120ms]",
                      value.speakers === n
                        ? "border-text-3 bg-surface-3 text-text-1"
                        : "border-line bg-transparent text-text-3 hover:border-text-3 hover:text-text-2",
                      disabled && "opacity-30 hover:border-line hover:text-text-3",
                    )}
                  >
                    {n}
                  </button>
                );
              })}
            </div>
          </Field>

          <Field label="길이">
            <Select value={value.length} options={LENGTHS} onValueChange={(v) => onChange({ ...value, length: v })} />
          </Field>

          <Field label="난이도">
            <Select value={value.level} options={LEVELS} onValueChange={(v) => onChange({ ...value, level: v })} />
          </Field>
        </div>

        <Field label="톤">
          <Input
            value={value.tone}
            placeholder="자연스럽고 편안한"
            onChange={(e) => onChange({ ...value, tone: e.target.value })}
          />
        </Field>
      </Card>

      {error ? <ErrorNote message={error} /> : null}

      {rawFallback ? (
        <Card className="flex flex-col gap-3 p-4">
          <div className="flex flex-col gap-1">
            <Legend>모델이 보낸 원문</Legend>
            <p className="t-body text-text-2">
              대본 형식을 두 번 다 읽지 못했습니다. 아래를 고쳐서 그대로 쓰거나, 다시 만들어보세요.
            </p>
          </div>
          <Textarea
            rows={12}
            className="t-meter text-[12px]"
            defaultValue={rawFallback}
            onChange={(e) => setRaw(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onGenerate}>
              다시 만들기
            </Button>
            <Button onClick={() => onUseRaw(raw || rawFallback)}>이 내용으로 진행</Button>
          </div>
        </Card>
      ) : null}

      <div className="flex items-center justify-end gap-3">
        <span className="t-legend">CTRL + ENTER</span>
        <Button disabled={!canGo} onClick={onGenerate}>
          {busy ? "대본을 쓰는 중" : "대본 만들기"}
          <CornerDownLeft className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}
