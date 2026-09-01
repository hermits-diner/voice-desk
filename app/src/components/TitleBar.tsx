/**
 * 커스텀 타이틀바.
 *
 * Windows 표준을 따른다: 창 제어는 오른쪽, 순서는 최소화 · 최대화 · 닫기,
 * 히트박스 46x32. 닫기만 호버 시 빨강으로 바뀐다.
 */
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Copy, Minus, Square, X } from "lucide-react";
import { useEffect, useState } from "react";

import { cn, isTauri } from "@/lib/utils";

function Control({
  onClick,
  label,
  danger,
  children,
}: {
  onClick: () => void;
  label: string;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={cn(
        "no-drag inline-flex h-8 w-[46px] items-center justify-center",
        "text-text-2 transition-colors duration-[120ms]",
        danger
          ? "hover:bg-lamp-clip hover:text-white"
          : "hover:bg-surface-3 hover:text-text-1",
      )}
    >
      {children}
    </button>
  );
}

export function TitleBar({ right }: { right?: React.ReactNode }) {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!isTauri()) return;
    const w = getCurrentWindow();
    let un: (() => void) | undefined;
    w.isMaximized().then(setMaximized);
    w.onResized(() => void w.isMaximized().then(setMaximized)).then((f) => (un = f));
    return () => un?.();
  }, []);

  const win = () => getCurrentWindow();

  return (
    <header className="drag-region flex h-8 shrink-0 items-center gap-3 border-b border-line bg-chrome pl-3">
      <span className="t-legend select-none text-text-2">VOICEDESK</span>
      <div className="flex-1" />
      <div className="no-drag flex items-center gap-2 pr-1">{right}</div>
      {isTauri() ? (
        <div className="flex items-center">
          <Control label="최소화" onClick={() => void win().minimize()}>
            <Minus className="size-3.5" />
          </Control>
          <Control
            label={maximized ? "이전 크기로" : "최대화"}
            onClick={() => void win().toggleMaximize()}
          >
            {maximized ? <Copy className="size-3" /> : <Square className="size-3" />}
          </Control>
          <Control label="닫기" danger onClick={() => void win().close()}>
            <X className="size-3.5" />
          </Control>
        </div>
      ) : null}
    </header>
  );
}
