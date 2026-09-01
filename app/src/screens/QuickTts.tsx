import { FolderOpen } from "lucide-react";
import { useState } from "react";

import { Waveform } from "@/components/Waveform";
import { Button, Card, ErrorNote, Field, Legend, Select, Textarea } from "@/components/ui";
import type { EngineName, JobStatus, Voice } from "@/lib/types";
import { humanSeconds, mmss, wordCount } from "@/lib/utils";

export function QuickTts({
  voices,
  job,
  peaks,
  currentTime,
  duration,
  onRun,
  onOpenFolder,
  error,
}: {
  voices: Voice[];
  job: JobStatus | null;
  peaks: Float32Array | null;
  currentTime: number;
  duration: number;
  onRun: (text: string, voice: string, engine: EngineName) => void;
  onOpenFolder: () => void;
  error: string | null;
}) {
  const [text, setText] = useState("");
  const [qEngine, setQEngine] = useState<EngineName>("vibevoice");
  const engineVoices = voices.filter((v) =>
    qEngine === "supertonic" ? v.engine === "supertonic" : v.engine !== "supertonic",
  );
  const [voice, setVoice] = useState<string | undefined>(undefined);
  const effVoice = engineVoices.some((v) => v.id === voice) ? voice : engineVoices[0]?.id;
  const busy = job != null && ["queued", "loading", "running", "encoding"].includes(job.state);
  const done = job?.state === "done";
  const words = wordCount(text);

  return (
    <div className="mx-auto flex w-full max-w-[720px] flex-col gap-5 px-6 py-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="t-display text-text-1">빠른 변환</h1>
        <p className="t-body text-text-2">대본 없이 텍스트를 바로 한 사람 목소리로 읽습니다.</p>
      </div>

      <Card className="flex flex-col gap-4 p-4">
        <Field label="텍스트" hint="Ctrl+Enter 로 바로 만들 수 있습니다.">
          <Textarea
            autoFocus
            rows={8}
            value={text}
            placeholder="읽을 문장을 넣어주세요."
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim() && effVoice && !busy) {
                e.preventDefault();
                onRun(text.trim(), effVoice, qEngine);
              }
            }}
          />
        </Field>
        <div className="flex items-end gap-4">
          <Field label="엔진" className="w-[160px]">
            <Select
              value={qEngine}
              options={[
                { value: "vibevoice", label: "VibeVoice", hint: "영어·중국어" },
                { value: "supertonic", label: "Supertonic", hint: "한국어·다국어" },
              ]}
              onValueChange={(v) => setQEngine(v as EngineName)}
            />
          </Field>
          <Field label="보이스" className="w-[240px]">
            <Select
              value={effVoice}
              options={engineVoices.map((v) => ({ value: v.id, label: v.label }))}
              onValueChange={setVoice}
            />
          </Field>
          <div className="flex flex-col gap-1.5">
            <Legend>예상 길이</Legend>
            <span className="t-meter pb-1.5 text-text-1">
              {words ? humanSeconds(words / 2.5) : "-"}
            </span>
          </div>
          <div className="flex-1" />
          <Button
            disabled={!text.trim() || !effVoice || busy}
            onClick={() => onRun(text.trim(), effVoice!, qEngine)}
          >
            {busy ? "만드는 중" : "음성 만들기"}
          </Button>
        </div>
      </Card>

      {error ? <ErrorNote message={error} /> : null}

      {job ? (
        <Card className="flex flex-col gap-3 p-4">
          <div className="flex items-center justify-between">
            <Legend>{done ? "완성" : "진행"}</Legend>
            <span className="t-meter text-text-2">
              {done ? mmss(duration) : `${Math.round(job.progress * 100)}% · ${mmss(job.elapsed)}`}
            </span>
          </div>
          <div className="h-[72px]">
            <Waveform
              peaks={peaks}
              progress={job.progress}
              currentTime={currentTime}
              duration={duration}
            />
          </div>
          {done ? (
            <div className="flex items-center gap-3">
              <span className="min-w-0 flex-1 truncate t-meter text-[11px] text-text-3">
                {job.audio_path}
              </span>
              <Button variant="outline" size="sm" onClick={onOpenFolder}>
                <FolderOpen className="size-3.5" />
                폴더 열기
              </Button>
            </div>
          ) : (
            <p className="t-body text-text-2">{job.message}</p>
          )}
        </Card>
      ) : null}
    </div>
  );
}
