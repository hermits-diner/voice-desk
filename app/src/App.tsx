import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Settings as SettingsIcon, Zap } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { HistorySidebar } from "@/components/HistorySidebar";
import { PracticeDialog } from "@/components/PracticeDialog";
import { Stepper } from "@/components/Stepper";
import { TitleBar } from "@/components/TitleBar";
import { TransportBar } from "@/components/TransportBar";
import { Button, Lamp } from "@/components/ui";
import { loadPeaks } from "@/components/Waveform";
import { api, pollJob, setPort } from "@/lib/api";
import { history, newHistoryItem } from "@/lib/history";
import { LivePlayer } from "@/lib/liveStream";
import type {
  EngineName, Health, HistoryItem, JobStatus, Script, ScriptRequest,
  SegmentTiming, Settings, Voice,
} from "@/lib/types";
import { ApiError } from "@/lib/types";
import { cn, isTauri } from "@/lib/utils";

import { BackendError } from "@/screens/BackendError";
import { Onboarding } from "@/screens/Onboarding";
import { QuickTts } from "@/screens/QuickTts";
import { RenderStep } from "@/screens/RenderStep";
import { ScriptStep } from "@/screens/ScriptStep";
import { SettingsPanel } from "@/screens/SettingsPanel";
import { TopicStep } from "@/screens/TopicStep";

type Boot = "starting" | "ready" | "failed";
type Tab = "main" | "quick";

const SAMPLE: Script = {
  title: "Sample check",
  format: "Conversation",
  segments: [
    { speaker: "A", text: "Okay, quick check. Can you hear this clearly?", note: null },
    { speaker: "B", text: "Loud and clear. That is everything working, then.", note: null },
  ],
};

export default function App() {
  const [boot, setBoot] = useState<Boot>("starting");
  const [bootError, setBootError] = useState("");
  const [bootLog, setBootLog] = useState<string[]>([]);
  const [bootWaited, setBootWaited] = useState(0);
  const [retrying, setRetrying] = useState(false);

  const [health, setHealth] = useState<Health | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [onboarding, setOnboarding] = useState(false);
  const [sampleState, setSampleState] = useState<"idle" | "running" | "done" | "error">("idle");

  const [tab, setTab] = useState<Tab>("main");
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [maxStep, setMaxStep] = useState<1 | 2 | 3>(1);
  const [collapsed, setCollapsed] = useState(false);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const [req, setReq] = useState<ScriptRequest>({
    topic: "", format: "Conversation", length: "medium", level: "B1",
    speakers: 2, tone: "자연스럽고 편안한",
  });
  const [script, setScript] = useState<Script | null>(null);
  const [engine, setEngine] = useState<EngineName>("vibevoice");
  const [voiceMap, setVoiceMap] = useState<Record<string, string>>({});

  const [scriptBusy, setScriptBusy] = useState(false);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [rawFallback, setRawFallback] = useState<string | null>(null);
  const [busySegment, setBusySegment] = useState<number | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  const [job, setJob] = useState<JobStatus | null>(null);
  const [quickJob, setQuickJob] = useState<JobStatus | null>(null);
  const [timings, setTimings] = useState<SegmentTiming[] | null>(null);
  const [peaks, setPeaks] = useState<Float32Array | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [loopSegment, setLoopSegment] = useState<number | null>(null);
  const [speed, setSpeed] = useState(1);
  const loopRef = useRef<number | null>(null);
  const timingsRef = useRef<SegmentTiming[] | null>(null);
  timingsRef.current = timings;
  loopRef.current = loopSegment;

  // 렌더 중 이어 듣기
  const liveRef = useRef<LivePlayer | null>(null);
  const [liveOn, setLiveOn] = useState(false);

  // Dia2 레퍼런스 클로닝 (화자 -> wav 경로)
  const [references, setReferences] = useState<Record<string, string>>({});

  // Anki · 발음 연습 · 모델 다운로드 · 시리즈
  const [ankiState, setAnkiState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [practiceIdx, setPracticeIdx] = useState<number | null>(null);
  const [downloads, setDownloads] = useState<Record<string, { progress: number; message: string; state: string }>>({});
  const [continueFrom, setContinueFrom] = useState<Script | null>(null);

  // 배치 큐 — 렌더 중에 추가로 요청한 작업들 (백엔드가 순서대로 처리한다)
  const [bgJobs, setBgJobs] = useState<
    { id: string; title: string; state: string; progress: number }[]
  >([]);

  /* ------------------------------------------------------------ 백엔드 기동 */

  // 백엔드는 뜨면서 torch 를 임포트한다. 이 PC 에서 20~30초가 걸리므로
  // 넉넉히 기다리고, 그동안 몇 초째인지 보여준다.
  const CONNECT_TIMEOUT_MS = 120_000;
  const connecting = useRef(false);

  const connect = useCallback(async (port: number) => {
    if (connecting.current) return false;
    connecting.current = true;
    setPort(port);
    setBoot("starting");
    const t0 = Date.now();
    try {
      while (Date.now() - t0 < CONNECT_TIMEOUT_MS) {
        try {
          const h = await api.health();
          setHealth(h);
          setBoot("ready");
          return true;
        } catch {
          setBootWaited(Math.round((Date.now() - t0) / 1000));
          await new Promise((r) => setTimeout(r, 600));
        }
      }
      setBootError(
        `백엔드가 ${Math.round(CONNECT_TIMEOUT_MS / 1000)}초 안에 응답하지 않았습니다. ` +
          "로그를 열어 원인을 확인해주세요.",
      );
      if (isTauri()) setBootLog(await invoke<string[]>("backend_log"));
      setBoot("failed");
      return false;
    } finally {
      connecting.current = false;
    }
  }, []);

  const startBackend = useCallback(async () => {
    setRetrying(true);
    setBoot("starting");
    setBootError("");
    setBootWaited(0);
    // 프로세스를 새로 띄우므로 진행 중이던 연결 시도는 버린다.
    connecting.current = false;
    try {
      if (isTauri()) {
        const port = await invoke<number>("backend_restart");
        await connect(port);
      } else {
        await connect(7861); // 브라우저에서 개발할 때
      }
    } catch (e) {
      setBootError(String(e));
      setBoot("failed");
      if (isTauri()) setBootLog(await invoke<string[]>("backend_log"));
    } finally {
      setRetrying(false);
    }
  }, [connect]);

  useEffect(() => {
    if (!isTauri()) {
      void connect(7861);
      return;
    }
    const unReady = listen<number>("backend-ready", (e) => void connect(e.payload));
    const unFail = listen<string>("backend-failed", async (e) => {
      setBootError(e.payload);
      setBootLog(await invoke<string[]>("backend_log"));
      setBoot("failed");
    });
    // 이미 떠 있는 경우(핫리로드 등)도 잡는다
    void invoke<{ running: boolean; port: number }>("backend_status").then((s) => {
      if (s.running) void connect(s.port);
    });
    return () => {
      void unReady.then((f) => f());
      void unFail.then((f) => f());
    };
  }, [connect]);

  /* --------------------------------------------------------------- 초기 로드 */

  useEffect(() => {
    if (boot !== "ready") return;
    void (async () => {
      const [s, v] = await Promise.all([api.settings(), api.voices()]);
      setSettings(s);
      setEngine(s.engine);
      setVoices(v);
      setItems(history.list());
      if (!localStorage.getItem("voicedesk.onboarded")) setOnboarding(true);
    })();
  }, [boot]);

  // 헬스는 느리게 폴링한다. 렌더 중엔 VRAM 이 움직이므로 조금 더 자주.
  // 의존성에 job 객체를 넣으면 폴링 때마다(700ms) 이 effect 가 다시 돌아
  // 인터벌이 리셋되고 결국 한 번도 발화하지 않는다. 불리언만 본다.
  const busy =
    (job != null && ["loading", "running", "encoding"].includes(job.state)) ||
    (quickJob != null && ["loading", "running", "encoding"].includes(quickJob.state));

  useEffect(() => {
    if (boot !== "ready") return;
    const tick = () => void api.health().then(setHealth).catch(() => {});
    tick();
    const id = setInterval(tick, busy ? 2000 : 8000);
    return () => clearInterval(id);
  }, [boot, busy]);

  /* ----------------------------------------------------------------- 테마 */

  useEffect(() => {
    const theme = settings?.theme ?? "system";
    const root = document.documentElement;
    const apply = () => {
      const dark =
        theme === "dark" ||
        (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
      root.setAttribute("data-theme", dark ? "dark" : "light");
    };
    apply();
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [settings?.theme]);

  /* ----------------------------------------------------------------- 오디오 */

  useEffect(() => {
    const a = new Audio();
    a.preload = "auto";
    audioRef.current = a;
    const onTime = () => {
      setCurrentTime(a.currentTime);
      const li = loopRef.current;
      const ts = timingsRef.current;
      if (li != null && ts?.[li] && a.currentTime >= ts[li].end - 0.02) {
        a.currentTime = ts[li].start;
      }
    };
    const onMeta = () => setDuration(a.duration || 0);
    const onEnd = () => setPlaying(false);
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    a.addEventListener("ended", onEnd);
    return () => {
      a.pause();
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("ended", onEnd);
    };
  }, []);

  // 재생 속도 (쉐도잉) — preservesPitch 는 Chromium 기본값이라 음정이 유지된다.
  // defaultPlaybackRate 도 함께 잡아 src 가 바뀌어도 속도가 유지되게 한다.
  useEffect(() => {
    const a = audioRef.current;
    if (a) {
      a.defaultPlaybackRate = speed;
      a.playbackRate = speed;
    }
  }, [speed]);

  const playingIndex =
    timings?.findIndex((t) => currentTime >= t.start && currentTime < t.end) ?? -1;

  const togglePlay = useCallback(() => {
    const a = audioRef.current;
    if (!a || !a.src) return;
    if (a.paused) {
      void a.play();
      setPlaying(true);
    } else {
      a.pause();
      setPlaying(false);
    }
  }, []);

  const seek = useCallback((s: number) => {
    const a = audioRef.current;
    if (!a || !a.src) return;
    a.currentTime = Math.max(0, s);
    setCurrentTime(a.currentTime);
  }, []);

  async function attachAudio(jobId: string) {
    const a = audioRef.current;
    if (!a) return;
    const url = api.audioUrl(jobId);
    a.src = url;
    a.currentTime = 0;
    setCurrentTime(0);
    setPlaying(false);
    try {
      setPeaks(await loadPeaks(url));
    } catch {
      setPeaks(null); // 디코드 실패해도 재생은 된다
    }
  }

  /* --------------------------------------------------------------- 대본 생성 */

  async function generateScript() {
    setScriptBusy(true);
    setScriptError(null);
    setRawFallback(null);
    try {
      const { script: s } = await api.makeScript({
        ...req,
        previous: continueFrom ?? undefined,
      });
      setContinueFrom(null);
      applyScript(s);
    } catch (e) {
      if (e instanceof ApiError) {
        setScriptError(e.message);
        if (e.raw) setRawFallback(e.raw);
      } else {
        setScriptError("대본을 만들지 못했습니다.");
      }
    } finally {
      setScriptBusy(false);
    }
  }

  function applyScript(s: Script) {
    setScript(s);
    const speakers = [...new Set(s.segments.map((x) => x.speaker))];
    const pool = voices.filter((v) => !v.has_bgm && v.language === "영어");
    const list = pool.length ? pool : voices;
    const map: Record<string, string> = {};
    speakers.forEach((sp, i) => {
      map[sp] = voiceMap[sp] ?? list[i % Math.max(1, list.length)]?.id;
    });
    setVoiceMap(map);
    setStep(2);
    setMaxStep((m) => (m > 2 ? m : 2));
    setJob(null);
    setTimings(null);
    setPeaks(null);
    const item = newHistoryItem(s, engine, map);
    history.upsert(item);
    setActiveId(item.id);
    setItems(history.list());
  }

  function useRawText(text: string) {
    try {
      const parsed = JSON.parse(text);
      applyScript(parsed as Script);
      setRawFallback(null);
      setScriptError(null);
    } catch {
      setScriptError("아직 JSON 형식이 아닙니다. 중괄호와 따옴표를 확인해주세요.");
    }
  }

  /* ------------------------------------------------------- 세그먼트 단위 동작 */

  async function previewSegment(i: number) {
    if (!script) return;
    setBusySegment(i);
    setRenderError(null);
    try {
      const seg = script.segments[i];
      // 노트는 발화에 넣지 않는다 — 모델이 괄호 내용을 그대로 읽는다.
      const started = await api.tts({
        text: seg.text,
        voice: voiceMap[seg.speaker],
        engine,
      });
      const fin = await pollJob(started.id, () => {});
      if (fin.state === "done") {
        const a = audioRef.current;
        if (a) {
          a.src = api.audioUrl(fin.id);
          a.currentTime = 0;
          void a.play();
        }
      } else {
        setRenderError(fin.error ?? "미리듣기를 만들지 못했습니다.");
      }
    } catch (e) {
      setRenderError(e instanceof Error ? e.message : "미리듣기에 실패했습니다.");
    } finally {
      setBusySegment(null);
    }
  }

  async function previewVoice(voiceId: string) {
    // 캐시 엔드포인트 — 첫 요청만 합성하고 이후에는 즉시 재생된다
    setBusySegment(-1);
    try {
      const a = audioRef.current;
      if (a) {
        a.src = api.voicePreviewUrl(voiceId);
        a.currentTime = 0;
        await a.play();
      }
    } catch {
      /* 렌더 중(409)이거나 재생 실패 — 조용히 넘긴다 */
    } finally {
      setBusySegment(null);
    }
  }

  function pickReference(speaker: string) {
    void (async () => {
      if (!isTauri()) return;
      const { open: openDialog } = await import("@tauri-apps/plugin-dialog");
      const picked = await openDialog({
        title: `${speaker} 화자의 레퍼런스 wav (5~30초)`,
        filters: [{ name: "오디오", extensions: ["wav", "mp3", "flac"] }],
      });
      if (typeof picked === "string") {
        setReferences((r) => {
          const next = { ...r };
          if (next[speaker] === picked) delete next[speaker];
          else next[speaker] = picked;
          return next;
        });
      }
    })();
  }

  async function regenerateSegment(i: number) {
    if (!script) return;
    setBusySegment(i);
    setRenderError(null);
    try {
      const { text, note, translation } = await api.regenerateSegment({
        script, index: i, model: req.model,
      });
      const segs = script.segments.slice();
      segs[i] = { ...segs[i], text, note: note ?? null, translation: translation ?? null };
      setScript({ ...script, segments: segs });
    } catch (e) {
      setRenderError(e instanceof Error ? e.message : "이 줄을 다시 만들지 못했습니다.");
    } finally {
      setBusySegment(null);
    }
  }

  /* ------------------------------------------------------------------ 렌더 */

  const startRender = useCallback(
    async (target?: Script, resumeFrom?: number) => {
      const s = target ?? script;
      if (!s) return;

      // 이미 렌더 중이면 새 작업은 큐로 보낸다. 백엔드가 GPU 를 직렬화하므로
      // 요청만 해 두면 순서대로 처리된다.
      const busyNow = job != null && ["queued", "loading", "running", "encoding"].includes(job.state);
      if (busyNow && resumeFrom == null) {
        const itemId = activeId;
        try {
          const started = await api.render({
            script: s,
            engine,
            voices: Object.entries(voiceMap).map(([speaker, voice]) => ({ speaker, voice })),
          });
          setBgJobs((q) => [...q, { id: started.id, title: s.title, state: started.state, progress: 0 }]);
          void pollJob(started.id, (st) => {
            setBgJobs((q) => q.map((e) => (e.id === started.id ? { ...e, state: st.state, progress: st.progress } : e)));
          }, 1500).then((fin) => {
            if (fin.state === "done" && itemId) {
              history.complete(itemId, {
                audioPath: fin.audio_path, timingPath: fin.timing_path,
                duration: fin.duration, timings: fin.timings,
              });
              setItems(history.list());
            }
            setTimeout(() => setBgJobs((q) => q.filter((e) => e.id !== started.id)), 6000);
          });
        } catch (e) {
          setRenderError(e instanceof Error ? e.message : "큐에 넣지 못했습니다.");
        }
        return;
      }

      const prevTimings = timings;
      const prevAudio = job?.audio_path ?? null;
      setStep(3);
      setMaxStep(3);
      setRenderError(null);
      setPeaks(null);
      setTimings(null);
      setLoopSegment(null);
      setAnkiState("idle");
      // 히스토리 재생에서 남은 오디오 상태를 비운다. duration 이 남아 있으면
      // 파형이 재생 위치(0초) 기준으로 그려져 진행 띠가 보이지 않는다.
      const a0 = audioRef.current;
      if (a0) {
        a0.pause();
        a0.removeAttribute("src");
      }
      setPlaying(false);
      setCurrentTime(0);
      setDuration(0);
      try {
        const canResume =
          resumeFrom != null && resumeFrom > 0 && prevAudio && prevTimings &&
          prevTimings.length >= resumeFrom;
        const started = await api.render({
          script: s,
          engine,
          voices: Object.entries(voiceMap).map(([speaker, voice]) => ({ speaker, voice })),
          references:
            engine === "dia2" && Object.keys(references).length ? references : undefined,
          ...(canResume
            ? {
                resume_from: resumeFrom,
                prev_audio_path: prevAudio!,
                prev_timings: prevTimings!,
              }
            : {}),
        });
        setJob(started);
        const fin = await pollJob(started.id, setJob);
        liveRef.current?.stop();
        setJob(fin);
        if (fin.state === "done") {
          setTimings(fin.timings);
          setDuration(fin.duration ?? 0);
          await attachAudio(fin.id);
          if (activeId) {
            history.complete(activeId, {
              audioPath: fin.audio_path,
              timingPath: fin.timing_path,
              duration: fin.duration,
              timings: fin.timings,
            });
            setItems(history.list());
          }
        } else if (fin.state === "error") {
          setRenderError(fin.error ?? "렌더가 실패했습니다.");
        }
      } catch (e) {
        setRenderError(e instanceof Error ? e.message : "렌더를 시작하지 못했습니다.");
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [script, engine, voiceMap, activeId, references, timings, job],
  );

  function toggleLive() {
    const j = tab === "quick" ? quickJob : job;
    if (!j) return;
    if (liveRef.current?.playing) {
      liveRef.current.stop();
      return;
    }
    const p = new LivePlayer(j.id, () => setLiveOn(false));
    liveRef.current = p;
    setLiveOn(true);
    void p.start();
  }

  async function exportAnki() {
    if (!job?.audio_path || !timings || !script) return;
    setAnkiState("busy");
    try {
      await api.exportAnki({ audio_path: job.audio_path, title: script.title, timings });
      setAnkiState("done");
    } catch (e) {
      setAnkiState("error");
      setRenderError(e instanceof Error ? e.message : "Anki 내보내기에 실패했습니다.");
    }
  }

  function nextEpisode() {
    if (!script) return;
    setContinueFrom(script);
    setReq((r) => ({ ...r, topic: "" }));
    setStep(1);
    setTab("main");
  }

  function startDownload(which: string) {
    void (async () => {
      try {
        const started = await api.downloadModel(which);
        setDownloads((d) => ({ ...d, [which]: { progress: 0, message: "시작", state: "running" } }));
        await pollJob(started.id, (s) => {
          setDownloads((d) => ({
            ...d,
            [which]: { progress: s.progress, message: s.message, state: s.state },
          }));
        }, 1500);
        void api.health().then(setHealth);
      } catch (e) {
        setDownloads((d) => ({
          ...d,
          [which]: { progress: 0, message: e instanceof Error ? e.message : "실패", state: "error" },
        }));
      }
    })();
  }

  async function runQuick(text: string, voice: string, quickEngine: EngineName) {
    setPeaks(null);
    try {
      const started = await api.tts({ text, voice, engine: quickEngine });
      setQuickJob(started);
      const fin = await pollJob(started.id, setQuickJob);
      setQuickJob(fin);
      if (fin.state === "done") {
        setDuration(fin.duration ?? 0);
        await attachAudio(fin.id);
      }
    } catch (e) {
      setRenderError(e instanceof Error ? e.message : "만들지 못했습니다.");
    }
  }

  /* --------------------------------------------------------------- 단축키 */

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA");

      if (e.key === " " && !typing) {
        e.preventDefault();
        togglePlay();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (job?.state === "done") void openFolder();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !typing) {
        e.preventDefault();
        if (step === 1 && req.topic.trim()) void generateScript();
        else if (step === 2 && script) void startRender();
      }
      if (e.key === "Escape" && showSettings) setShowSettings(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function openFolder() {
    const path = job?.audio_path ?? quickJob?.audio_path;
    if (!path) return;
    if (isTauri()) await invoke("reveal_in_explorer", { path });
  }

  /* --------------------------------------------------------------- 렌더링 */

  if (boot !== "ready") {
    return (
      <div className="flex h-full flex-col bg-surface-1">
        <TitleBar />
        {boot === "starting" ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3">
            <Lamp tone="ready" pulse label="백엔드를 시작하는 중" />
            {/* 모델 라이브러리를 불러오느라 20~30초 걸린다. 멈춘 것처럼 보이지 않게 초를 센다. */}
            <span className="t-meter text-text-3">
              {bootWaited > 3 ? `${bootWaited}초째 · 모델 라이브러리를 불러오는 중` : ""}
            </span>
          </div>
        ) : (
          <BackendError
            message={bootError || "백엔드를 시작하지 못했습니다."}
            log={bootLog}
            onRetry={() => void startBackend()}
            retrying={retrying}
          />
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-surface-1">
      <TitleBar
        right={
          <>
            <Button
              variant={tab === "quick" ? "primary" : "ghost"}
              size="sm"
              onClick={() => setTab(tab === "quick" ? "main" : "quick")}
            >
              <Zap className="size-3.5" />
              빠른 변환
            </Button>
            <Button
              variant="ghost"
              size="iconSm"
              aria-label="설정"
              onClick={() => setShowSettings(true)}
            >
              <SettingsIcon className="size-3.5" />
            </Button>
          </>
        }
      />

      <div className="flex min-h-0 flex-1">
        <HistorySidebar
          items={items}
          activeId={activeId}
          collapsed={collapsed}
          onToggle={() => setCollapsed((v) => !v)}
          onNew={() => {
            setScript(null);
            setJob(null);
            setTimings(null);
            setPeaks(null);
            setActiveId(null);
            setStep(1);
            setMaxStep(1);
            setTab("main");
          }}
          onDelete={(id) => {
            history.remove(id);
            setItems(history.list());
            if (id === activeId) setActiveId(null);
          }}
          onOpen={(it) => {
            setScript(it.script);
            setEngine(it.engine);
            setVoiceMap(it.voices);
            setActiveId(it.id);
            setTimings(it.timings);
            setStep(it.step);
            setMaxStep(it.step);
            setTab("main");
            setPeaks(null);
            setLoopSegment(null);
            // 렌더까지 끝난 항목이면 저장된 mp3 를 그대로 다시 재생할 수 있게 한다.
            if (it.audioPath && it.duration != null) {
              setJob({
                id: "history", state: "done", kind: "render", progress: 1,
                segment_index: null, segment_total: null, message: "저장본",
                elapsed: 0, eta: null, audio_path: it.audioPath,
                script_path: null, timing_path: it.timingPath,
                duration: it.duration, timings: it.timings,
                error_code: null, error: null,
              });
              setDuration(it.duration);
              const a = audioRef.current;
              if (a) {
                const url = api.audioFileUrl(it.audioPath);
                a.src = url;
                a.currentTime = 0;
                setCurrentTime(0);
                setPlaying(false);
                loadPeaks(url).then(setPeaks).catch(() => setPeaks(null));
              }
            } else {
              setJob(null);
            }
          }}
        />

        <main className="flex min-w-0 flex-1 flex-col">
          {onboarding ? (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <Onboarding
                health={health}
                onRefreshHealth={() => void api.health().then(setHealth)}
                downloads={downloads}
                onDownload={startDownload}
                sampleState={sampleState}
                onSample={async () => {
                  setSampleState("running");
                  try {
                    const started = await api.render({ script: SAMPLE, engine: "vibevoice" });
                    const fin = await pollJob(started.id, setJob);
                    setJob(fin);
                    if (fin.state === "done") {
                      setTimings(fin.timings);
                      setDuration(fin.duration ?? 0);
                      await attachAudio(fin.id);
                      setSampleState("done");
                    } else setSampleState("error");
                  } catch {
                    setSampleState("error");
                  }
                }}
                onDone={() => {
                  localStorage.setItem("voicedesk.onboarded", "1");
                  setOnboarding(false);
                  setJob(null);
                }}
              />
            </div>
          ) : tab === "quick" ? (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <QuickTts
                voices={voices}
                job={quickJob}
                peaks={peaks}
                currentTime={currentTime}
                duration={duration}
                onRun={runQuick}
                onOpenFolder={openFolder}
                error={renderError}
              />
            </div>
          ) : (
            <>
              <div className="flex h-11 shrink-0 items-center border-b border-line px-4">
                <Stepper
                  step={step}
                  maxReached={maxStep}
                  onGo={(s) => setStep(s)}
                />
              </div>

              <div className={cn("min-h-0 flex-1", step === 1 ? "overflow-y-auto" : "")}>
                {step === 1 ? (
                  <TopicStep
                    value={req}
                    onChange={setReq}
                    onGenerate={() => void generateScript()}
                    busy={scriptBusy}
                    error={scriptError}
                    rawFallback={rawFallback}
                    onUseRaw={useRawText}
                    hasKey={health?.has_gemini_key ?? false}
                    onOpenSettings={() => setShowSettings(true)}
                  />
                ) : step === 2 && script ? (
                  <ScriptStep
                    script={script}
                    onChange={(s) => {
                      setScript(s);
                      if (activeId) {
                        const it = history.get(activeId);
                        if (it) {
                          history.upsert({ ...it, script: s, title: s.title, voices: voiceMap, engine });
                          setItems(history.list());
                        }
                      }
                    }}
                    voices={voices}
                    voiceMap={voiceMap}
                    onVoiceMap={setVoiceMap}
                    engine={engine}
                    onEngine={setEngine}
                    onPreviewSegment={(i) => void previewSegment(i)}
                    onRegenerateSegment={(i) => void regenerateSegment(i)}
                    onPreviewVoice={(v) => void previewVoice(v)}
                    onRender={() => void startRender()}
                    busySegment={busySegment}
                    error={renderError}
                    references={references}
                    onPickReference={pickReference}
                  />
                ) : step === 3 && script ? (
                  <RenderStep
                    script={script}
                    job={job}
                    peaks={peaks}
                    currentTime={currentTime}
                    duration={duration}
                    timings={timings}
                    playingIndex={playingIndex >= 0 ? playingIndex : null}
                    loopSegment={loopSegment}
                    onSeek={seek}
                    onPlaySegment={(i) => {
                      const t = timings?.[i];
                      if (!t) return;
                      seek(t.start);
                      const a = audioRef.current;
                      if (a?.paused) {
                        void a.play();
                        setPlaying(true);
                      }
                    }}
                    onToggleLoopSegment={(i) => setLoopSegment((cur) => (cur === i ? null : i))}
                    onOpenFolder={openFolder}
                    onBackToScript={() => setStep(2)}
                    onRetry={() => void startRender()}
                    onExportAnki={() => void exportAnki()}
                    ankiState={ankiState}
                    onNextEpisode={nextEpisode}
                    onResumeFrom={(i) => void startRender(undefined, i)}
                    onPractice={(i) => setPracticeIdx(i)}
                  />
                ) : null}
              </div>
            </>
          )}
        </main>
      </div>

      <TransportBar
        health={health}
        job={tab === "quick" ? quickJob : job}
        playing={playing}
        currentTime={currentTime}
        duration={duration}
        timings={timings}
        loopSegment={loopSegment}
        speed={speed}
        live={liveOn}
        onTogglePlay={togglePlay}
        onSeek={seek}
        onToggleLoop={() =>
          setLoopSegment((cur) => (cur == null ? (playingIndex >= 0 ? playingIndex : null) : null))
        }
        onCancel={() => {
          const j = tab === "quick" ? quickJob : job;
          if (j) void api.cancel(j.id);
          liveRef.current?.stop();
        }}
        onSpeed={setSpeed}
        onToggleLive={toggleLive}
      />

      {bgJobs.length ? (
        <div className="fixed bottom-14 right-3 z-30 flex w-[260px] flex-col gap-1 rounded-[--radius-2] border border-line bg-surface-2 p-2">
          <span className="t-legend px-1">QUEUE</span>
          {bgJobs.map((q) => (
            <div key={q.id} className="flex items-center gap-2 px-1 py-0.5">
              <span
                className={cn(
                  "size-[6px] shrink-0 rounded-full",
                  q.state === "done" ? "bg-lamp-ready"
                  : q.state === "error" ? "bg-lamp-clip"
                  : "bg-lamp-signal lamp-pulse",
                )}
              />
              <span className="min-w-0 flex-1 truncate t-ui text-text-2">{q.title}</span>
              <span className="t-meter text-[11px] text-text-3">
                {q.state === "done" ? "완료" : q.state === "error" ? "실패" : `${Math.round(q.progress * 100)}%`}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <PracticeDialog
        open={practiceIdx != null}
        onOpenChange={(v) => !v && setPracticeIdx(null)}
        audioUrl={
          job?.id === "history" && job.audio_path
            ? api.audioFileUrl(job.audio_path)
            : job
              ? api.audioUrl(job.id)
              : null
        }
        timing={practiceIdx != null ? (timings?.[practiceIdx] ?? null) : null}
      />

      <SettingsPanel
        open={showSettings}
        onOpenChange={setShowSettings}
        settings={settings}
        health={health}
        onSave={async (patch) => {
          const s = await api.saveSettings(patch);
          setSettings(s);
          setEngine(s.engine);
        }}
        onRestartBackend={() => void startBackend()}
      />
    </div>
  );
}
