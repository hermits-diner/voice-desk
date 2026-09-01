import { RotateCcw } from "lucide-react";
import { useState } from "react";

import { Button, Card, Legend } from "@/components/ui";

/**
 * 백엔드가 안 뜬 상태의 전체 화면 폴백.
 * 원인과 다음 행동만 말하고, 자세한 로그는 접어둔다.
 */
export function BackendError({
  message,
  log,
  onRetry,
  retrying,
}: {
  message: string;
  log: string[];
  onRetry: () => void;
  retrying: boolean;
}) {
  const [open, setOpen] = useState(false);
  const tail = log.slice(-40);

  return (
    <div className="flex h-full items-center justify-center px-8">
      <div className="flex w-full max-w-[560px] flex-col gap-5">
        <div className="flex items-center gap-2.5">
          <span className="size-[6px] rounded-full bg-lamp-clip" aria-hidden />
          <Legend>BACKEND</Legend>
        </div>

        <h1 className="t-display text-text-1">백엔드가 응답하지 않습니다</h1>
        <p data-selectable className="t-body text-text-2">
          {message}
        </p>

        <div className="flex items-center gap-3">
          <Button onClick={onRetry} disabled={retrying}>
            <RotateCcw className="size-3.5" />
            {retrying ? "다시 시작하는 중" : "다시 시작"}
          </Button>
          {tail.length ? (
            <Button variant="ghost" onClick={() => setOpen((v) => !v)}>
              {open ? "로그 접기" : "로그 보기"}
            </Button>
          ) : null}
        </div>

        {open && tail.length ? (
          <Card className="max-h-[280px] overflow-auto bg-surface-1 p-3">
            <pre
              data-selectable
              className="whitespace-pre-wrap break-all t-meter text-[11px] leading-[17px] text-text-2"
            >
              {tail.join("\n")}
            </pre>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
