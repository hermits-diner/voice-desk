export type SpeakerId = "NARRATOR" | "A" | "B" | "C" | "D";
export type ScriptFormat = "Narration" | "Conversation" | "Interview" | "Monologue";
export type LengthPreset = "short" | "medium" | "long";
export type Cefr = "A2" | "B1" | "B2" | "C1";
export type EngineName = "vibevoice" | "dia2" | "supertonic";

export interface Segment {
  speaker: SpeakerId;
  text: string;
  note: string | null;
  translation?: string | null;
}

export interface Script {
  title: string;
  format: ScriptFormat;
  segments: Segment[];
}

export interface ScriptRequest {
  topic: string;
  format: ScriptFormat;
  length: LengthPreset;
  level: Cefr;
  speakers: number;
  tone: string;
  model?: string;
  translate?: boolean;
  /** 시리즈: 이전 화 대본을 주면 이어지는 다음 화를 쓴다 */
  previous?: Script | null;
}

export interface Voice {
  id: string;
  label: string;
  language: string;
  gender: string | null;
  engine: string;
  has_bgm: boolean;
  path: string | null;
}

export interface SegmentTiming {
  index: number;
  speaker: SpeakerId;
  text: string;
  start: number;
  end: number;
  translation?: string | null;
}

export type JobState =
  | "queued" | "loading" | "running" | "encoding" | "done" | "error" | "cancelled";

export interface JobStatus {
  id: string;
  state: JobState;
  kind: "render" | "tts";
  progress: number;
  segment_index: number | null;
  segment_total: number | null;
  message: string;
  elapsed: number;
  eta: number | null;
  audio_path: string | null;
  script_path: string | null;
  timing_path: string | null;
  duration: number | null;
  timings: SegmentTiming[] | null;
  error_code: string | null;
  error: string | null;
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  engine: EngineName;
  engine_loaded: string | null;
  cuda: boolean;
  device: string | null;
  vram_total_gb: number | null;
  vram_used_gb: number | null;
  models: Record<string, boolean>;
  has_gemini_key: boolean;
}

export interface Settings {
  host: string;
  port: number;
  engine: EngineName;
  output_dir: string;
  audio_format: "mp3" | "wav";
  bitrate_kbps: number;
  loudness_lufs: number;
  sample_rate: number;
  gap_speaker_ms: number;
  gap_paragraph_ms: number;
  vv_ddpm_steps: number;
  vv_cfg_scale: number;
  vv_polish: boolean;
  dia2_cuda_graph: boolean;
  dia2_temperature: number;
  dia2_top_k: number;
  dia2_cfg_scale: number;
  dia2_max_retries: number;
  supertonic_lang: string;
  supertonic_speed: number;
  supertonic_steps: number;
  export_subtitles: boolean;
  script_translation: boolean;
  gemini_model: string;
  theme: "system" | "dark" | "light";
}

export interface HistoryItem {
  id: string;
  createdAt: number;
  title: string;
  format: ScriptFormat;
  engine: EngineName;
  script: Script;
  voices: Record<string, string>;
  audioPath: string | null;
  timingPath: string | null;
  duration: number | null;
  timings: SegmentTiming[] | null;
  step: 1 | 2 | 3;
}

export class ApiError extends Error {
  code: string;
  raw?: string;
  constructor(code: string, message: string, raw?: string) {
    super(message);
    this.code = code;
    this.raw = raw;
  }
}
