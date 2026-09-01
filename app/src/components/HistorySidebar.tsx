import { PanelLeftClose, PanelLeftOpen, Plus, Trash2 } from "lucide-react";
import { useMemo } from "react";

import { groupLabel } from "@/lib/history";
import type { HistoryItem } from "@/lib/types";
import { cn, mmss, speakerLabel } from "@/lib/utils";
import { Button, Legend } from "./ui";

export function HistorySidebar({
  items,
  activeId,
  collapsed,
  onToggle,
  onOpen,
  onDelete,
  onNew,
}: {
  items: HistoryItem[];
  activeId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onOpen: (item: HistoryItem) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
}) {
  const groups = useMemo(() => {
    const map = new Map<string, HistoryItem[]>();
    for (const it of items) {
      const k = groupLabel(it.createdAt);
      const arr = map.get(k) ?? [];
      arr.push(it);
      map.set(k, arr);
    }
    return [...map.entries()];
  }, [items]);

  if (collapsed) {
    return (
      <aside className="flex w-11 shrink-0 flex-col items-center gap-1 border-r border-line bg-surface-1 py-2">
        <Button variant="ghost" size="icon" onClick={onToggle} aria-label="히스토리 펼치기">
          <PanelLeftOpen className="size-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={onNew} aria-label="새로 만들기">
          <Plus className="size-4" />
        </Button>
      </aside>
    );
  }

  return (
    <aside className="flex w-[260px] shrink-0 flex-col border-r border-line bg-surface-1">
      <div className="flex h-11 shrink-0 items-center gap-1 border-b border-line px-3">
        <Legend className="flex-1">HISTORY</Legend>
        <Button variant="ghost" size="iconSm" onClick={onNew} aria-label="새로 만들기">
          <Plus className="size-3.5" />
        </Button>
        <Button variant="ghost" size="iconSm" onClick={onToggle} aria-label="히스토리 접기">
          <PanelLeftClose className="size-3.5" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {items.length === 0 ? (
          <p className="px-2 py-6 text-[12px] leading-5 text-text-3">
            만든 대본이 여기에 쌓입니다. 어느 단계에서든 다시 열어 이어갈 수 있습니다.
          </p>
        ) : (
          groups.map(([label, list]) => (
            <div key={label} className="mb-3">
              <Legend className="px-2 pb-1.5">{label}</Legend>
              <div className="flex flex-col gap-px">
                {list.map((it) => (
                  <div
                    key={it.id}
                    className={cn(
                      "group flex items-center rounded-[--radius-1]",
                      "transition-colors duration-[120ms]",
                      it.id === activeId ? "bg-surface-3" : "hover:bg-surface-2",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => onOpen(it)}
                      className="flex min-w-0 flex-1 flex-col items-start gap-0.5 px-2 py-1.5 text-left"
                    >
                      <span className="w-full truncate t-ui text-text-1">{it.title}</span>
                      <span className="t-meter text-[11px] text-text-3">
                        {summarize(it)}
                      </span>
                    </button>
                    <button
                      type="button"
                      aria-label={`${it.title} 삭제`}
                      onClick={() => onDelete(it.id)}
                      className={cn(
                        "mr-1 hidden size-6 shrink-0 items-center justify-center rounded-[--radius-1]",
                        "text-text-3 hover:bg-surface-1 hover:text-lamp-clip group-hover:flex",
                      )}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}

function summarize(it: HistoryItem): string {
  const speakers = new Set(it.script.segments.map((s) => s.speaker));
  const who =
    speakers.size === 1 && speakers.has("NARRATOR")
      ? speakerLabel("NARRATOR")
      : `${speakers.size}인`;
  const len = it.duration != null ? mmss(it.duration) : "대본만";
  return `${who} · ${len}`;
}
