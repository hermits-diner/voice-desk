import { api } from "./api";

/**
 * 렌더 중 미리 듣기 — 합성이 끝난 부분부터 이어서 재생한다.
 *
 * 백엔드가 int16 PCM 을 쌓아 두면 700ms 마다 새 조각을 받아 Web Audio 로
 * 이어 붙인다. 탐색은 지원하지 않는다(완성본 플레이어가 담당).
 */
export class LivePlayer {
  private ctx: AudioContext | null = null;
  private nextTime = 0;
  private fromByte = 0;
  private timer: ReturnType<typeof setInterval> | null = null;
  private jobId: string;
  private onEnd: () => void;

  constructor(jobId: string, onEnd: () => void) {
    this.jobId = jobId;
    this.onEnd = onEnd;
  }

  get playing(): boolean {
    return this.ctx !== null;
  }

  async start(): Promise<void> {
    if (this.ctx) return;
    this.ctx = new AudioContext();
    await this.ctx.resume();
    this.nextTime = this.ctx.currentTime + 0.15;
    this.fromByte = 0;
    const tick = async () => {
      if (!this.ctx) return;
      try {
        const { data, total, sr, state } = await api.fetchPcm(this.jobId, this.fromByte);
        if (total < this.fromByte) {
          // 백엔드가 처음부터 다시 시작했다 (재시드 재시도)
          this.fromByte = 0;
          this.nextTime = this.ctx.currentTime + 0.15;
          return;
        }
        if (sr > 0 && data.length > 0) {
          const f32 = new Float32Array(data.length);
          for (let i = 0; i < data.length; i++) f32[i] = data[i] / 32768;
          const buf = this.ctx.createBuffer(1, f32.length, sr);
          buf.copyToChannel(f32, 0);
          const src = this.ctx.createBufferSource();
          src.buffer = buf;
          src.connect(this.ctx.destination);
          const at = Math.max(this.nextTime, this.ctx.currentTime + 0.05);
          src.start(at);
          this.nextTime = at + buf.duration;
          this.fromByte = total;
        }
        if (state === "done" || state === "error" || state === "cancelled") {
          // 남은 조각까지 스케줄된 뒤 자연히 끝난다
          const remain = Math.max(0, this.nextTime - this.ctx.currentTime);
          setTimeout(() => this.stop(), remain * 1000 + 300);
          if (this.timer) clearInterval(this.timer);
          this.timer = null;
        }
      } catch {
        /* 다음 틱에 다시 */
      }
    };
    this.timer = setInterval(() => void tick(), 700);
    void tick();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    if (this.ctx) {
      void this.ctx.close();
      this.ctx = null;
      this.onEnd();
    }
  }
}
