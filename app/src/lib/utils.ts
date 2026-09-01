import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { SpeakerId } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** 0:00 형식. 계측 표시는 항상 tabular-nums 로 렌더한다. */
export function mmss(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return "--:--";
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function humanSeconds(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return "-";
  if (seconds < 60) return `${Math.round(seconds)}초`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s ? `${m}분 ${s}초` : `${m}분`;
}

/** 화자 라벨. NARRATOR 는 '나레이션'으로 읽는다. */
export function speakerLabel(sp: SpeakerId): string {
  return sp === "NARRATOR" ? "나레이션" : sp;
}

/**
 * 화자 구분은 색이 아니라 밝기와 라벨로 한다. 앰버는 신호 전용이므로
 * 화자 태그에 쓰지 않는다 (DIRECTION.md 2절).
 */
export function speakerTone(sp: SpeakerId): string {
  switch (sp) {
    case "NARRATOR":
      return "bg-surface-3 text-text-2 border-line";
    case "A":
      return "bg-surface-3 text-text-1 border-line";
    case "B":
      return "bg-surface-2 text-text-1 border-line";
    case "C":
      return "bg-surface-3 text-text-2 border-line-soft";
    default:
      return "bg-surface-2 text-text-2 border-line-soft";
  }
}

export function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}
