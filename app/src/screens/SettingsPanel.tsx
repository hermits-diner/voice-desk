import * as Dialog from "@radix-ui/react-dialog";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { Check, Eye, EyeOff, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button, Card, ErrorNote, Field, Input, Lamp, Legend, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { Health, Settings } from "@/lib/types";
import { cn, isTauri } from "@/lib/utils";

export function SettingsPanel({
  open,
  onOpenChange,
  settings,
  health,
  onSave,
  onRestartBackend,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  settings: Settings | null;
  health: Health | null;
  onSave: (patch: Partial<Settings>) => Promise<void>;
  onRestartBackend: () => void;
}) {
  const [draft, setDraft] = useState<Settings | null>(settings);
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [portChanged, setPortChanged] = useState(false);

  useEffect(() => {
    if (open) {
      setDraft(settings);
      setMsg(null);
      setErr(null);
      setPortChanged(false);
      setKey("");
    }
  }, [open, settings]);

  if (!draft) return null;
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => {
    setDraft({ ...draft, [k]: v });
    if (k === "port") setPortChanged(true);
  };

  async function pickFolder() {
    if (!isTauri()) return;
    const picked = await openDialog({ directory: true, defaultPath: draft!.output_dir });
    if (typeof picked === "string") set("output_dir", picked);
  }

  async function saveKey() {
    setErr(null);
    try {
      await api.setGeminiKey(key);
      setKey("");
      setMsg("키를 자격 증명 관리자에 저장했습니다.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "키를 저장하지 못했습니다.");
    }
  }

  async function loadModels() {
    setErr(null);
    try {
      setModels(await api.geminiModels());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "모델 목록을 받지 못했습니다.");
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/45" />
        <Dialog.Content
          className={cn(
            "fixed right-0 top-8 bottom-0 z-50 flex w-[440px] flex-col",
            "border-l border-line bg-surface-1 outline-none",
          )}
        >
          <div className="flex h-11 shrink-0 items-center border-b border-line px-4">
            <Dialog.Title className="flex-1 t-ui text-text-1">설정</Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="iconSm" aria-label="닫기">
                <X className="size-3.5" />
              </Button>
            </Dialog.Close>
          </div>

          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-4">
            {err ? <ErrorNote message={err} /> : null}
            {msg ? (
              <div className="flex items-center gap-2 t-body text-lamp-ready">
                <Check className="size-4" />
                {msg}
              </div>
            ) : null}

            <Section title="GEMINI">
              <div className="flex items-center gap-2">
                <Lamp
                  tone={health?.has_gemini_key ? "ready" : "clip"}
                  label={health?.has_gemini_key ? "키 등록됨" : "키 없음"}
                />
              </div>
              <Field label="API 키" hint="Windows 자격 증명 관리자에 저장되며 로그에 남지 않습니다.">
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Input
                      type={showKey ? "text" : "password"}
                      value={key}
                      placeholder={health?.has_gemini_key ? "새 키로 바꾸기" : "키 붙여넣기"}
                      onChange={(e) => setKey(e.target.value)}
                      className="pr-8"
                    />
                    <button
                      type="button"
                      aria-label={showKey ? "키 숨기기" : "키 보기"}
                      onClick={() => setShowKey((v) => !v)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-text-3 hover:text-text-1"
                    >
                      {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                    </button>
                  </div>
                  <Button disabled={!key.trim()} onClick={saveKey}>
                    저장
                  </Button>
                </div>
              </Field>
              <Field label="모델">
                <div className="flex gap-2">
                  {models.length ? (
                    <Select
                      className="flex-1"
                      value={draft.gemini_model}
                      options={models.map((m) => ({ value: m, label: m }))}
                      onValueChange={(v) => set("gemini_model", v)}
                    />
                  ) : (
                    <Input
                      className="flex-1"
                      value={draft.gemini_model}
                      onChange={(e) => set("gemini_model", e.target.value)}
                    />
                  )}
                  <Button variant="outline" onClick={loadModels}>
                    목록 받기
                  </Button>
                </div>
              </Field>
            </Section>

            <Section title="엔진">
              <Field label="기본 엔진" hint="GPU 엔진은 하나만 상주하고, Supertonic은 CPU라 나란히 돕니다.">
                <Select
                  value={draft.engine}
                  options={[
                    { value: "vibevoice", label: "VibeVoice 1.5B", hint: "영·중 · 화자 4명 · 긴 대화" },
                    { value: "dia2", label: "Dia2 2B", hint: "영어 · 화자 2명 · 줄 재합성 · 클로닝" },
                    { value: "supertonic", label: "Supertonic 3", hint: "한국어·다국어 · CPU" },
                  ]}
                  onValueChange={(v) => set("engine", v)}
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="VibeVoice DDPM 스텝" hint="줄이면 조금 빨라지지만 발화가 급해집니다.">
                  <Input
                    type="number"
                    min={3}
                    max={30}
                    value={draft.vv_ddpm_steps}
                    onChange={(e) => set("vv_ddpm_steps", Number(e.target.value))}
                  />
                </Field>
                <Field label="Dia2 CUDA 그래프" hint="끄면 Windows에서 4배 느려집니다.">
                  <Select
                    value={draft.dia2_cuda_graph ? "on" : "off"}
                    options={[
                      { value: "on", label: "켬 (권장)" },
                      { value: "off", label: "끔" },
                    ]}
                    onValueChange={(v) => set("dia2_cuda_graph", v === "on")}
                  />
                </Field>
                <Field label="금속성 잔향 정리" hint="VibeVoice 구절 사이 쇠소리를 익스팬더로 누릅니다.">
                  <Select
                    value={draft.vv_polish ? "on" : "off"}
                    options={[
                      { value: "on", label: "켬 (권장)" },
                      { value: "off", label: "끔" },
                    ]}
                    onValueChange={(v) => set("vv_polish", v === "on")}
                  />
                </Field>
                <Field label="Supertonic 언어" hint="ko 고정이 가장 안정적입니다. na는 자동.">
                  <Select
                    value={draft.supertonic_lang}
                    options={[
                      { value: "ko", label: "한국어 (ko)" },
                      { value: "en", label: "영어 (en)" },
                      { value: "ja", label: "일본어 (ja)" },
                      { value: "na", label: "자동 (na)" },
                    ]}
                    onValueChange={(v) => set("supertonic_lang", v)}
                  />
                </Field>
              </div>
              <div className="flex items-center justify-between">
                <span className="t-body text-text-2">
                  상주 중: {health?.engine_loaded ?? "없음"}
                </span>
                <Button variant="outline" size="sm" onClick={() => void api.unloadEngine()}>
                  GPU에서 내리기
                </Button>
              </div>
            </Section>

            <Section title="출력">
              <Field label="저장 폴더">
                <div className="flex gap-2">
                  <Input
                    className="flex-1"
                    value={draft.output_dir}
                    onChange={(e) => set("output_dir", e.target.value)}
                  />
                  {isTauri() ? (
                    <Button variant="outline" onClick={pickFolder}>
                      찾기
                    </Button>
                  ) : null}
                </div>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="형식">
                  <Select
                    value={draft.audio_format}
                    options={[
                      { value: "mp3", label: "mp3" },
                      { value: "wav", label: "wav" },
                    ]}
                    onValueChange={(v) => set("audio_format", v)}
                  />
                </Field>
                <Field label="비트레이트">
                  <Select
                    value={String(draft.bitrate_kbps)}
                    options={["96", "128", "192", "256", "320"].map((v) => ({
                      value: v,
                      label: `${v} kbps`,
                    }))}
                    onValueChange={(v) => set("bitrate_kbps", Number(v))}
                  />
                </Field>
                <Field label="자막(.srt) 함께 저장">
                  <Select
                    value={draft.export_subtitles ? "on" : "off"}
                    options={[
                      { value: "on", label: "켬" },
                      { value: "off", label: "끔" },
                    ]}
                    onValueChange={(v) => set("export_subtitles", v === "on")}
                  />
                </Field>
                <Field label="한국어 번역 병기" hint="대본 생성 시 세그먼트별 번역을 함께 받습니다.">
                  <Select
                    value={draft.script_translation ? "on" : "off"}
                    options={[
                      { value: "on", label: "켬" },
                      { value: "off", label: "끔" },
                    ]}
                    onValueChange={(v) => set("script_translation", v === "on")}
                  />
                </Field>
              </div>
            </Section>

            <Section title="서버">
              <Field
                label="포트"
                hint={portChanged ? "저장 뒤 백엔드를 다시 시작해야 적용됩니다." : undefined}
              >
                <Input
                  type="number"
                  value={draft.port}
                  onChange={(e) => set("port", Number(e.target.value))}
                />
              </Field>
              <div className="flex items-center justify-between">
                <span className="t-meter text-[11px] text-text-3">
                  {health?.device ?? "GPU 없음"}
                  {health?.vram_total_gb ? ` · ${health.vram_total_gb} GB` : ""}
                </span>
                <Button variant="outline" size="sm" onClick={onRestartBackend}>
                  백엔드 다시 시작
                </Button>
              </div>
            </Section>

            <Section title="모양">
              <Field label="테마">
                <Select
                  value={draft.theme}
                  options={[
                    { value: "system", label: "시스템 따라가기" },
                    { value: "dark", label: "어둡게" },
                    { value: "light", label: "밝게" },
                  ]}
                  onValueChange={(v) => set("theme", v)}
                />
              </Field>
            </Section>

            <Section title="캐시">
              <div className="flex items-center justify-between">
                <span className="t-body text-text-2">Dia2 구간 캐시</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    const r = await api.clearCache();
                    setMsg(`구간 캐시 ${r.removed}개를 지웠습니다.`);
                  }}
                >
                  비우기
                </Button>
              </div>
            </Section>
          </div>

          <div className="flex shrink-0 items-center justify-end gap-2 border-t border-line px-4 py-3">
            <Dialog.Close asChild>
              <Button variant="ghost">닫기</Button>
            </Dialog.Close>
            <Button
              onClick={async () => {
                setErr(null);
                try {
                  await onSave(draft);
                  setMsg("저장했습니다.");
                } catch (e) {
                  setErr(e instanceof Error ? e.message : "저장하지 못했습니다.");
                }
              }}
            >
              저장
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="flex flex-col gap-4 p-3.5">
      <Legend>{title}</Legend>
      {children}
    </Card>
  );
}
