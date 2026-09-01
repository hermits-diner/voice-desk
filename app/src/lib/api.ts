import {
  ApiError, Health, JobStatus, Script, ScriptRequest, SegmentTiming, Settings, Voice,
} from "./types";

let BASE = "http://127.0.0.1:7860";

export function setPort(port: number) {
  BASE = `http://127.0.0.1:${port}`;
}
export function baseUrl() {
  return BASE;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("offline", "백엔드가 응답하지 않습니다. 다시 시작을 눌러주세요.");
  }
  if (!res.ok) {
    let code = String(res.status);
    let message = `요청이 실패했습니다 (${res.status}).`;
    let raw: string | undefined;
    try {
      const body = await res.json();
      const d = body?.detail;
      if (typeof d === "string") {
        message = d;
      } else if (d && typeof d === "object") {
        code = d.code ?? code;
        message = d.message ?? message;
        raw = d.raw;
      }
    } catch {
      /* 본문이 JSON 이 아니면 기본 문구를 쓴다 */
    }
    throw new ApiError(code, message, raw);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => call<Health>("/health"),
  voices: () => call<Voice[]>("/voices"),

  makeScript: (req: ScriptRequest) =>
    call<{ script: Script; model: string }>("/script", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  geminiModels: () => call<string[]>("/gemini/models"),

  /** 앞뒤 맥락을 주고 한 줄만 다시 쓴다. */
  regenerateSegment: (body: { script: Script; index: number; model?: string }) =>
    call<{ text: string; note: string | null; translation: string | null }>("/script/segment", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  render: (body: {
    script: Script;
    engine?: string;
    voices?: { speaker: string; voice: string }[];
    seed?: number;
    references?: Record<string, string>;
    resume_from?: number;
    prev_audio_path?: string;
    prev_timings?: SegmentTiming[];
  }) => call<JobStatus>("/render", { method: "POST", body: JSON.stringify(body) }),

  tts: (body: { text: string; voice?: string; engine?: string }) =>
    call<JobStatus>("/tts", { method: "POST", body: JSON.stringify(body) }),

  job: (id: string) => call<JobStatus>(`/jobs/${id}`),
  cancel: (id: string) => call<JobStatus>(`/jobs/${id}/cancel`, { method: "POST" }),
  audioUrl: (id: string) => `${BASE}/jobs/${id}/audio`,
  /** 히스토리에서 다시 연 항목의 저장 mp3. 출력 폴더 안의 파일만 준다. */
  audioFileUrl: (path: string) => `${BASE}/audio?path=${encodeURIComponent(path)}`,

  /** 보이스 샘플 — 첫 요청에서 만들어지고 이후 캐시로 즉시 온다. */
  voicePreviewUrl: (voiceId: string) => `${BASE}/voices/${encodeURIComponent(voiceId)}/preview`,

  jobsList: () => call<JobStatus[]>("/jobs"),

  /** 렌더 중 미리 듣기용 PCM. (데이터, 전체 바이트, 샘플레이트, 작업 상태) */
  fetchPcm: async (jobId: string, fromByte: number) => {
    const res = await fetch(`${BASE}/jobs/${jobId}/pcm?from_byte=${fromByte}`);
    if (!res.ok) throw new ApiError(String(res.status), "PCM 을 받지 못했습니다.");
    const buf = await res.arrayBuffer();
    return {
      data: new Int16Array(buf),
      total: Number(res.headers.get("X-Pcm-Total") ?? 0),
      sr: Number(res.headers.get("X-Pcm-Sr") ?? 0),
      state: res.headers.get("X-Job-State") ?? "",
    };
  },

  exportAnki: (body: { audio_path: string; title: string; timings: SegmentTiming[] }) =>
    call<{ path: string; cards: number }>("/export/anki", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  downloadModel: (which: string) =>
    call<JobStatus>("/models/download", {
      method: "POST",
      body: JSON.stringify({ which }),
    }),

  settings: () => call<Settings>("/settings"),
  saveSettings: (patch: Partial<Settings>) =>
    call<Settings>("/settings", { method: "PUT", body: JSON.stringify(patch) }),
  setGeminiKey: (key: string) =>
    call<{ has_key: boolean }>("/settings/gemini-key", {
      method: "POST",
      body: JSON.stringify({ key }),
    }),
  clearCache: () => call<{ removed: number }>("/cache/clear", { method: "POST" }),
  unloadEngine: () => call<{ loaded: string | null }>("/engine/unload", { method: "POST" }),
};

/** 작업이 끝날 때까지 폴링한다. 매 갱신마다 onTick 을 부른다. */
export async function pollJob(
  id: string,
  onTick: (s: JobStatus) => void,
  intervalMs = 700,
): Promise<JobStatus> {
  for (;;) {
    const s = await api.job(id);
    onTick(s);
    if (s.state === "done" || s.state === "error" || s.state === "cancelled") return s;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
