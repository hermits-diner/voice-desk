/**
 * 발음 연습 — 구간을 듣고, 따라 말하고, 되들어 비교한다.
 *
 * 채점은 하지 않는다. 원문과 내 녹음을 번갈아 들으며 귀로 맞추는 도구다.
 * 녹음은 메모리에만 있고 저장하지 않는다.
 */
import * as Dialog from "@radix-ui/react-dialog";
import { Mic, Pause, Play, Square, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { SegmentTiming } from "@/lib/types";
import { cn, mmss } from "@/lib/utils";
import { Button, ErrorNote, Legend } from "./ui";

const SPEEDS = [1, 0.75, 0.5];

export function PracticeDialog({
  open,
  onOpenChange,
  audioUrl,
  timing,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  audioUrl: string | null;
  timing: SegmentTiming | null;
}) {
  const originalRef = useRef<HTMLAudioElement | null>(null);
  const stopAtRef = useRef<number>(0);
  const [playingOrig, setPlayingOrig] = useState(false);
  const [speed, setSpeed] = useState(1);

  const [recording, setRecording] = useState(false);
  const [recUrl, setRecUrl] = useState<string | null>(null);
  const [playingRec, setPlayingRec] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recAudioRef = useRef<HTMLAudioElement | null>(null);
  const [recSeconds, setRecSeconds] = useState(0);

  // 열 때마다 초기화
  useEffect(() => {
    if (!open) return;
    setMicError(null);
    setRecUrl(null);
    setSpeed(1);
    setRecSeconds(0);
    return () => {
      originalRef.current?.pause();
      recorderRef.current?.stream.getTracks().forEach((t) => t.stop());
      recorderRef.current = null;
      if (recUrl) URL.revokeObjectURL(recUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    const a = new Audio();
    originalRef.current = a;
    const onTime = () => {
      if (a.currentTime >= stopAtRef.current - 0.02) {
        a.pause();
        setPlayingOrig(false);
      }
    };
    const onPause = () => setPlayingOrig(false);
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("pause", onPause);
    return () => {
      a.pause();
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("pause", onPause);
    };
  }, []);

  function playOriginal() {
    const a = originalRef.current;
    if (!a || !audioUrl || !timing) return;
    if (a.src !== audioUrl) a.src = audioUrl;
    a.playbackRate = speed;
    a.currentTime = timing.start;
    stopAtRef.current = timing.end;
    void a.play();
    setPlayingOrig(true);
  }

  async function toggleRecord() {
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    setMicError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (recUrl) URL.revokeObjectURL(recUrl);
        setRecUrl(URL.createObjectURL(new Blob(chunks, { type: rec.mimeType })));
        setRecording(false);
      };
      recorderRef.current = rec;
      rec.start();
      setRecording(true);
      setRecSeconds(0);
      const t0 = Date.now();
      const id = setInterval(() => {
        if (rec.state !== "recording") {
          clearInterval(id);
          return;
        }
        setRecSeconds((Date.now() - t0) / 1000);
      }, 200);
    } catch {
      setMicError("마이크를 쓸 수 없습니다. Windows 설정에서 마이크 권한을 확인해주세요.");
    }
  }

  function playRecording() {
    if (!recUrl) return;
    if (!recAudioRef.current) recAudioRef.current = new Audio();
    const a = recAudioRef.current;
    if (playingRec) {
      a.pause();
      setPlayingRec(false);
      return;
    }
    a.src = recUrl;
    a.onended = () => setPlayingRec(false);
    void a.play();
    setPlayingRec(true);
  }

  const dur = timing ? timing.end - timing.start : 0;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/45" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[520px] -translate-x-1/2 -translate-y-1/2",
            "rounded-[--radius-2] border border-line bg-surface-2 outline-none",
          )}
        >
          <div className="flex h-11 items-center border-b border-line px-4">
            <Dialog.Title className="flex-1 t-ui text-text-1">발음 연습</Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="iconSm" aria-label="닫기">
                <X className="size-3.5" />
              </Button>
            </Dialog.Close>
          </div>

          <div className="flex flex-col gap-4 p-4">
            {timing ? (
              <div className="flex flex-col gap-1">
                <Legend>{`SEGMENT · ${mmss(timing.start)} – ${mmss(timing.end)} (${dur.toFixed(1)}S)`}</Legend>
                <p data-selectable className="t-body text-text-1">{timing.text}</p>
                {timing.translation ? (
                  <p className="text-[12px] leading-5 text-text-2">{timing.translation}</p>
                ) : null}
              </div>
            ) : null}

            {micError ? <ErrorNote message={micError} /> : null}

            <div className="grid grid-cols-3 gap-2">
              <div className="flex flex-col items-center gap-2 rounded-[--radius-2] border border-line-soft p-3">
                <Legend>1 듣기</Legend>
                <Button variant="outline" size="icon" onClick={playOriginal}
                        aria-label="원문 듣기">
                  {playingOrig ? <Pause className="size-4" /> : <Play className="size-4" />}
                </Button>
                <button
                  type="button"
                  onClick={() => {
                    const i = SPEEDS.indexOf(speed);
                    setSpeed(SPEEDS[(i + 1) % SPEEDS.length] ?? 1);
                  }}
                  className="t-meter text-[11px] text-text-3 hover:text-text-1"
                >
                  {speed}×
                </button>
              </div>

              <div className="flex flex-col items-center gap-2 rounded-[--radius-2] border border-line-soft p-3">
                <Legend>2 말하기</Legend>
                <Button
                  variant={recording ? "danger" : "outline"}
                  size="icon"
                  onClick={() => void toggleRecord()}
                  aria-label={recording ? "녹음 끝내기" : "녹음 시작"}
                >
                  {recording ? <Square className="size-4" /> : <Mic className="size-4" />}
                </Button>
                <span className={cn("t-meter text-[11px]",
                                    recording ? "text-lamp-clip" : "text-text-3")}>
                  {recording ? `${recSeconds.toFixed(1)}s` : recUrl ? "녹음됨" : "대기"}
                </span>
              </div>

              <div className="flex flex-col items-center gap-2 rounded-[--radius-2] border border-line-soft p-3">
                <Legend>3 비교</Legend>
                <Button variant="outline" size="icon" disabled={!recUrl}
                        onClick={playRecording} aria-label="내 녹음 듣기">
                  {playingRec ? <Pause className="size-4" /> : <Play className="size-4" />}
                </Button>
                <span className="t-meter text-[11px] text-text-3">내 목소리</span>
              </div>
            </div>

            <p className="text-[11px] leading-4 text-text-3">
              녹음은 저장되지 않고 이 창을 닫으면 사라집니다. 원문을 느리게(0.5×) 들으며
              따라 말해보고, 익숙해지면 원속으로 돌아오세요.
            </p>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
