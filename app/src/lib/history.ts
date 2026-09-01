import type { HistoryItem, Script, SegmentTiming } from "./types";

const KEY = "voicedesk.history.v1";
const LIMIT = 200;

function read(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function write(list: HistoryItem[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, LIMIT)));
  } catch {
    /* 용량 초과 등은 무시한다. 히스토리는 편의 기능이지 원본이 아니다. */
  }
}

export const history = {
  list(): HistoryItem[] {
    return read().sort((a, b) => b.createdAt - a.createdAt);
  },

  get(id: string): HistoryItem | undefined {
    return read().find((h) => h.id === id);
  },

  /** 대본 단계에서 저장. 렌더 전에도 히스토리에 남아 이어서 열 수 있다. */
  upsert(item: HistoryItem): HistoryItem {
    const list = read();
    const i = list.findIndex((h) => h.id === item.id);
    if (i >= 0) list[i] = item;
    else list.unshift(item);
    write(list);
    return item;
  },

  complete(
    id: string,
    patch: {
      audioPath: string | null;
      timingPath: string | null;
      duration: number | null;
      timings: SegmentTiming[] | null;
    },
  ) {
    const list = read();
    const i = list.findIndex((h) => h.id === id);
    if (i >= 0) {
      list[i] = { ...list[i], ...patch, step: 3 };
      write(list);
    }
  },

  remove(id: string) {
    write(read().filter((h) => h.id !== id));
  },

  clear() {
    write([]);
  },
};

export function newHistoryItem(
  script: Script,
  engine: HistoryItem["engine"],
  voices: Record<string, string>,
): HistoryItem {
  return {
    id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`,
    createdAt: Date.now(),
    title: script.title,
    format: script.format,
    engine,
    script,
    voices,
    audioPath: null,
    timingPath: null,
    duration: null,
    timings: null,
    step: 2,
  };
}

/** '오늘 / 어제 / 9월 1일' 로 묶는다. */
export function groupLabel(ts: number): string {
  const d = new Date(ts);
  const today = new Date();
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((startOf(today) - startOf(d)) / 86_400_000);
  if (diff === 0) return "오늘";
  if (diff === 1) return "어제";
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}
