import { Check, Eye, EyeOff } from "lucide-react";
import { useState } from "react";

import { Button, Card, ErrorNote, Field, Input, Lamp, Legend } from "@/components/ui";
import { api } from "@/lib/api";
import type { Health } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * 첫 실행 온보딩 — Gemini 키 -> 모델/GPU 확인 -> 샘플 1회 생성.
 * 세 단계를 한 화면에 세로로 두고, 끝난 단계는 ready 램프로 표시한다.
 */
export interface DownloadState {
  progress: number;
  message: string;
  state: string;
}

export function Onboarding({
  health,
  onRefreshHealth,
  onSample,
  sampleState,
  onDone,
  downloads,
  onDownload,
}: {
  health: Health | null;
  onRefreshHealth: () => void;
  onSample: () => void;
  sampleState: "idle" | "running" | "done" | "error";
  onDone: () => void;
  downloads: Record<string, DownloadState>;
  onDownload: (which: string) => void;
}) {
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const hasKey = health?.has_gemini_key ?? false;
  const gpuOk = health?.cuda ?? false;
  const modelsOk = Boolean(health?.models?.vibevoice || health?.models?.dia2);
  const envOk = gpuOk && modelsOk && Boolean(health?.models?.ffmpeg);

  function dlAction(which: string, ok: boolean) {
    if (ok) return null;
    const d = downloads[which];
    if (d && (d.state === "running" || d.state === "queued")) {
      return (
        <span className="t-meter text-[11px] text-lamp-signal">
          {Math.round(d.progress * 100)}% · {d.message}
        </span>
      );
    }
    return (
      <Button variant="outline" size="sm" onClick={() => onDownload(which)}>
        내려받기
      </Button>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[620px] flex-col gap-6 px-6 pb-10 pt-8">
      <div className="flex flex-col gap-1.5">
        <Legend>SETUP</Legend>
        <h1 className="t-display text-text-1">세 가지만 확인하면 시작합니다</h1>
      </div>

      <Step n={1} title="Gemini 키" done={hasKey}>
        <p className="t-body text-text-2">
          대본을 쓰는 데 씁니다. Windows 자격 증명 관리자에 저장되고 코드나 로그에는 남지 않습니다.
        </p>
        {hasKey ? (
          <Lamp tone="ready" label="등록됨" />
        ) : (
          <>
            <Field label="API 키">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    type={show ? "text" : "password"}
                    value={key}
                    placeholder="키 붙여넣기"
                    onChange={(e) => setKey(e.target.value)}
                    className="pr-8"
                  />
                  <button
                    type="button"
                    aria-label={show ? "키 숨기기" : "키 보기"}
                    onClick={() => setShow((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-text-3 hover:text-text-1"
                  >
                    {show ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                  </button>
                </div>
                <Button
                  disabled={!key.trim() || saving}
                  onClick={async () => {
                    setErr(null);
                    setSaving(true);
                    try {
                      await api.setGeminiKey(key.trim());
                      setKey("");
                      onRefreshHealth();
                    } catch (e) {
                      setErr(e instanceof Error ? e.message : "키를 저장하지 못했습니다.");
                    } finally {
                      setSaving(false);
                    }
                  }}
                >
                  저장
                </Button>
              </div>
            </Field>
            {err ? <ErrorNote message={err} /> : null}
          </>
        )}
      </Step>

      <Step n={2} title="GPU와 모델" done={envOk}>
        <div className="flex flex-col gap-2">
          <Row
            ok={gpuOk}
            label="GPU"
            value={health?.device ?? "찾지 못했습니다"}
            hint="CUDA를 쓸 수 있는 그래픽카드가 필요합니다."
          />
          <Row
            ok={Boolean(health?.models?.vibevoice)}
            label="VibeVoice 1.5B"
            value={health?.models?.vibevoice ? "C:\\ai\\models\\VibeVoice-1.5B" : "없음 · 5.1GB"}
            hint="기본 엔진(영어·중국어)입니다."
            action={dlAction("vibevoice", Boolean(health?.models?.vibevoice))}
          />
          <Row
            ok={Boolean(health?.models?.dia2)}
            label="Dia2 2B"
            value={health?.models?.dia2 ? "C:\\ai\\models\\Dia2-2B" : "없음 · 7.6GB (선택)"}
            hint="보조 엔진이라 없어도 시작할 수 있습니다."
            action={dlAction("dia2", Boolean(health?.models?.dia2))}
          />
          <Row
            ok={Boolean(health?.models?.supertonic)}
            label="Supertonic 3"
            value={health?.models?.supertonic ? "C:\\ai\\models\\supertonic-3" : "없음 · 0.4GB (선택)"}
            hint="한국어 엔진입니다. CPU로 돌아 가볍습니다."
            action={dlAction("supertonic", Boolean(health?.models?.supertonic))}
          />
          <Row
            ok={Boolean(health?.models?.ffmpeg)}
            label="ffmpeg"
            value={health?.models?.ffmpeg ? "동봉본 사용" : "없음"}
            hint="backend\\bin\\ffmpeg.exe 가 있어야 mp3로 저장합니다."
          />
        </div>
        <Button variant="outline" size="sm" onClick={onRefreshHealth} className="self-start">
          다시 확인
        </Button>
      </Step>

      <Step n={3} title="샘플 한 번 만들어보기" done={sampleState === "done"}>
        <p className="t-body text-text-2">
          짧은 2인 대화를 한 번 렌더해 전체 흐름이 도는지 봅니다. 1분쯤 걸립니다.
        </p>
        <div className="flex items-center gap-3">
          <Button disabled={!envOk || sampleState === "running"} onClick={onSample}>
            {sampleState === "running" ? "만드는 중" : "샘플 만들기"}
          </Button>
          {sampleState === "done" ? <Lamp tone="ready" label="완료" /> : null}
          {sampleState === "error" ? <Lamp tone="clip" label="실패" /> : null}
        </div>
      </Step>

      <div className="flex justify-end">
        <Button onClick={onDone} disabled={!envOk}>
          시작하기
        </Button>
      </div>
    </div>
  );
}

function Step({
  n,
  title,
  done,
  children,
}: {
  n: number;
  title: string;
  done: boolean;
  children: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "flex size-5 items-center justify-center rounded-full border t-legend",
            done ? "border-lamp-ready text-lamp-ready" : "border-line text-text-3",
          )}
        >
          {done ? <Check className="size-3" /> : n}
        </span>
        <span className="t-ui text-text-1">{title}</span>
      </div>
      <div className="flex flex-col gap-3 pl-[30px]">{children}</div>
    </Card>
  );
}

function Row({
  ok,
  label,
  value,
  hint,
  action,
}: {
  ok: boolean;
  label: string;
  value: string;
  hint: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <span
        className={cn("mt-[7px] size-[6px] shrink-0 rounded-full", ok ? "bg-lamp-ready" : "bg-lamp-clip")}
        aria-hidden
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-baseline gap-2">
          <span className="t-ui text-text-1">{label}</span>
          <span className="truncate t-meter text-[11px] text-text-3">{value}</span>
        </div>
        {!ok ? <span className="text-[11px] leading-4 text-text-3">{hint}</span> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
