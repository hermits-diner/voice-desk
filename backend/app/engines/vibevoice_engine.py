"""VibeVoice-1.5B 엔진.

대본 전체를 "Speaker N: 텍스트" 한 덩어리로 넘겨 한 번에 렌더한다. 화자 최대 4명.

세그먼트 타임스탬프는 생성된 토큰 열에서 정확히 뽑는다. 측정으로 확인한 사실:
  - 확산 토큰(<|vision_pad|>) 1개 == 정확히 3200 샘플 (24kHz / 7.5Hz)
  - 턴이 끝날 때마다 speech_end(<|vision_end|>) 토큰이 하나씩 나온다
  - 턴 4개 대본에서 END 4개, 경계가 실제 발화 길이와 일치 (오차 0 샘플)
"""
from __future__ import annotations

import logging
import re
import threading

import numpy as np
import torch

from ..config import VIBEVOICE_MODEL
from ..schemas import Script, SegmentTiming
from ..timing import TimingQuality, end_anchors, segment_bounds, text_weight
from .base import CancelFn, Engine, EngineError, ProgressFn, RenderResult, estimate_seconds

log = logging.getLogger(__name__)

SAMPLE_RATE = 24000
SAMPLES_PER_FRAME = 3200  # 확산 토큰 1개당 샘플 수


class _ProgressStreamer:
    """generate() 가 확산 스텝마다 호출하는 훅.

    AudioStreamer 를 상속하는 대신 필요한 인터페이스(put / end / finished_flags)만
    구현한다. generate() 는 이 셋만 쓴다. finished_flags 를 True 로 만들면
    생성 루프가 다음 스텝에서 빠져나오므로 취소에도 쓴다.
    """

    def __init__(self, on_progress: ProgressFn, should_cancel: CancelFn, expected_s: float,
                 on_audio=None):  # noqa: ANN001
        self.finished_flags = [False]
        self._frames = 0
        self._on_progress = on_progress
        self._should_cancel = should_cancel
        self._on_audio = on_audio
        self._expected = max(expected_s, 1.0)
        self.cancelled = False

    def put(self, audio_chunks, sample_indices) -> None:  # noqa: ANN001
        self._frames += 1
        done_s = self._frames * SAMPLES_PER_FRAME / SAMPLE_RATE
        if self._should_cancel():
            self.cancelled = True
            self.finished_flags[0] = True
            return
        if self._on_audio is not None:
            try:
                chunk = audio_chunks[0].detach().to(torch.float32).cpu().numpy().reshape(-1)
                self._on_audio(chunk, SAMPLE_RATE)
            except Exception:  # noqa: BLE001
                self._on_audio = None  # 미리 듣기는 부가 기능 — 렌더를 막지 않는다
        self._on_progress(done_s, self._expected, f"{done_s:.0f}초 합성")

    def end(self, sample_indices=None) -> None:  # noqa: ANN001
        self.finished_flags[0] = True


def _speaker_numbers(script: Script) -> dict[str, int]:
    """대본의 화자 라벨을 등장 순서대로 Speaker 1..4 에 매핑한다."""
    order = script.speakers()
    if len(order) > 4:
        raise EngineError(
            "too_many_speakers",
            f"화자가 {len(order)}명입니다. VibeVoice는 4명까지만 지원합니다.",
        )
    return {sp: i + 1 for i, sp in enumerate(order)}


def build_prompt(script: Script) -> str:
    """대본 -> "Speaker N: 텍스트" 형식.

    note(연기 지시)는 프롬프트에 넣지 않는다. 괄호 지시로 붙여 보내면
    VibeVoice 가 감정 지시로 해석하지 않고 "cheerful, relaxed" 를 그대로
    읽는 것을 실사용에서 확인했다. note 는 화면 표시와 대본 재생성에만 쓴다.

    줄바꿈은 턴 구분이므로 텍스트 안의 개행은 공백으로 눕힌다.
    """
    nums = _speaker_numbers(script)
    lines: list[str] = []
    for seg in script.segments:
        text = re.sub(r"\s+", " ", seg.text).strip()
        text = text.replace("’", "'")
        lines.append(f"Speaker {nums[seg.speaker]}: {text}")
    return "\n".join(lines)


def _timings_from_tokens(
    generated: list[int],
    speech_end_id: int,
    speech_diffusion_id: int,
    script: Script,
    audio: np.ndarray,
) -> tuple[list[SegmentTiming], TimingQuality]:
    """토큰 열 + 파형에서 세그먼트 경계를 뽑는다. 자세한 근거는 timing.py 참조."""
    anchors = end_anchors(generated, speech_end_id, speech_diffusion_id)
    weights = [text_weight(s.text) for s in script.segments]
    total_s = audio.shape[-1] / SAMPLE_RATE
    bounds, quality = segment_bounds(weights, total_s, anchors, audio)

    timings: list[SegmentTiming] = []
    prev = 0.0
    for i, seg in enumerate(script.segments):
        timings.append(SegmentTiming(
            index=i, speaker=seg.speaker, text=seg.text,
            start=round(prev, 3), end=bounds[i],
            translation=seg.translation,
        ))
        prev = bounds[i]
    return timings, quality


class VibeVoiceEngine(Engine):
    name = "vibevoice"

    def __init__(self, ddpm_steps: int = 10, cfg_scale: float = 1.3,
                 polish: bool = True) -> None:
        self._model = None
        self._processor = None
        self._lock = threading.Lock()
        self.ddpm_steps = ddpm_steps
        self.cfg_scale = cfg_scale
        self.polish = polish  # 금속성 잔향 정리 (audio.polish)

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            if not (VIBEVOICE_MODEL / "model.safetensors.index.json").exists():
                raise EngineError(
                    "model_missing",
                    "VibeVoice 가중치가 없습니다. 설정에서 내려받기를 시작해주세요.",
                )
            from vibevoice.modular.modeling_vibevoice_inference import (
                VibeVoiceForConditionalGenerationInference,
            )
            from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor

            try:
                self._processor = VibeVoiceProcessor.from_pretrained(str(VIBEVOICE_MODEL))
                model = VibeVoiceForConditionalGenerationInference.from_pretrained(
                    str(VIBEVOICE_MODEL),
                    torch_dtype=torch.bfloat16,
                    device_map="cuda",
                    # flash-attn 은 설치 금지 제약이므로 SDPA 고정
                    attn_implementation="sdpa",
                )
            except torch.cuda.OutOfMemoryError as exc:
                raise EngineError(
                    "vram",
                    "GPU 메모리가 부족해 모델을 올리지 못했습니다. 다른 GPU 프로그램을 닫고 다시 시도해주세요.",
                ) from exc
            model.eval()
            model.set_ddpm_inference_steps(num_steps=self.ddpm_steps)
            self._model = model

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self._processor = None
            torch.cuda.empty_cache()

    # 이보다 빨리 "말한" 것으로 나오면 대본을 건너뛴 것이다. 실측: 정상 출력은
    # 2.5~3.2 단어/초, 조기 EOS 로 잘린 출력은 8.2 단어/초였다.
    MAX_PLAUSIBLE_WPS = 4.5
    MAX_RETRIES = 2

    def render(
        self,
        script: Script,
        voice_map: dict[str, str],
        *,
        on_progress: ProgressFn,
        should_cancel: CancelFn,
        seed: int | None = None,
        on_audio=None,  # noqa: ANN001
    ) -> RenderResult:
        """대본 전체를 한 번에 렌더한다.

        do_sample=False 라도 확산 헤드는 매 스텝 노이즈를 뽑으므로 음향 경로는
        확률적이고, 그 결과가 LLM 에 되먹임되어 드물게 조기 EOS 가 난다
        (410단어 대본이 50초로 잘리는 사례를 실측). 시드를 고정해 재현 가능하게
        만들고, 출력이 너무 짧으면 시드를 바꿔 다시 시도한다.
        """
        self.load()
        assert self._model is not None and self._processor is not None

        base_seed = seed if seed is not None else 1234
        words = sum(len(s.text.split()) for s in script.segments)
        notes_extra: list[str] = []

        result = None
        for attempt in range(self.MAX_RETRIES + 1):
            if attempt > 0 and on_audio is not None:
                on_audio(None, SAMPLE_RATE)  # 미리 듣기 버퍼 리셋 (재시드 재시도)
            torch.manual_seed(base_seed + attempt * 7919)
            torch.cuda.manual_seed_all(base_seed + attempt * 7919)
            result = self._render_once(script, voice_map, on_progress, should_cancel, on_audio)
            duration = result.audio.shape[-1] / SAMPLE_RATE
            wps = words / duration if duration > 0 else float("inf")
            if wps <= self.MAX_PLAUSIBLE_WPS:
                break
            log.warning(
                "출력이 너무 짧음 (시도 %d): %d단어 / %.1fs = %.1f 단어/초 -> 재시드",
                attempt + 1, words, duration, wps,
            )
            if attempt < self.MAX_RETRIES:
                notes_extra.append(
                    f"{attempt + 1}번째 출력이 대본보다 짧아 다시 합성했습니다."
                )
        else:
            notes_extra.append(
                "여러 번 시도해도 출력이 대본보다 짧습니다. 대본을 나눠서 렌더해보세요."
            )

        assert result is not None
        result.notes.extend(notes_extra)
        return result

    def _render_once(
        self,
        script: Script,
        voice_map: dict[str, str],
        on_progress: ProgressFn,
        should_cancel: CancelFn,
        on_audio=None,  # noqa: ANN001
    ) -> RenderResult:
        from ..voices import resolve

        prompt = build_prompt(script)
        order = script.speakers()
        voice_paths = [str(resolve(voice_map.get(sp))) for sp in order]

        proc = self._processor
        inputs = proc(
            text=[prompt], voice_samples=[voice_paths],
            padding=True, return_tensors="pt", return_attention_mask=True,
        )
        inputs = {k: (v.to("cuda") if torch.is_tensor(v) else v) for k, v in inputs.items()}
        n_in = int(inputs["input_ids"].shape[1])

        streamer = _ProgressStreamer(on_progress, should_cancel, estimate_seconds(script),
                                     on_audio)
        on_progress(0.0, estimate_seconds(script), "합성 시작")

        try:
            out = self._model.generate(
                **inputs,
                max_new_tokens=None,
                cfg_scale=self.cfg_scale,
                tokenizer=proc.tokenizer,
                generation_config={"do_sample": False},
                verbose=False,
                is_prefill=True,
                audio_streamer=streamer,
            )
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            raise EngineError(
                "vram",
                "GPU 메모리가 부족합니다. 대본을 나누거나 설정에서 엔진을 하나만 켜두세요.",
            ) from exc

        if streamer.cancelled:
            raise EngineError("cancelled", "렌더를 취소했습니다.")

        if not out.speech_outputs or out.speech_outputs[0] is None:
            raise EngineError("no_audio", "오디오가 생성되지 않았습니다. 대본을 확인해주세요.")

        audio_t = out.speech_outputs[0].detach().to(torch.float32).cpu().reshape(-1)
        audio = audio_t.numpy()

        # 타임스탬프 계산 전에 정리한다. 협대역 억제는 길이를 바꾸지 않고
        # 꼬리 트림은 끝만 줄이므로 END 앵커(내부 경계)는 그대로 유효하다.
        polish_notes: list[str] = []
        if self.polish:
            from ..audio import polish as _polish

            audio, polish_notes = _polish(audio, SAMPLE_RATE)

        tok = proc.tokenizer
        generated = out.sequences[0].tolist()[n_in:]
        timings, quality = _timings_from_tokens(
            generated, tok.speech_end_id, tok.speech_diffusion_id, script, audio,
        )

        notes: list[str] = [quality.describe(), *polish_notes]
        if getattr(out, "reach_max_step_sample", None) is not None:
            try:
                if bool(out.reach_max_step_sample[0]):
                    notes.append("생성 길이 상한에 도달해 대본 끝까지 읽지 못했을 수 있습니다.")
            except (IndexError, TypeError):
                pass

        return RenderResult(
            audio=audio, sample_rate=SAMPLE_RATE, timings=timings,
            timings_estimated=not quality.exact, notes=notes,
        )
