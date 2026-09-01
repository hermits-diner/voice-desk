# VoiceDesk 제품 명세서

| | |
|---|---|
| 문서 버전 | 1.0 (2026-09-01) |
| 대상 제품 | VoiceDesk v0.1.0 |
| 상태 | 구현 완료 — 본 문서는 구현·실측으로 검증된 내용만 기술한다 |
| 관련 문서 | `SETUP.md`(환경·이슈·재현), `TESTING.md`(수용 테스트), `design/DIRECTION.md`(디자인 시스템) |

이 문서 하나로 제품을 다시 만들 수 있도록, 요구사항 → 아키텍처 → 컴포넌트 명세 → 산출물 형식 → 수용 기준 순으로 기술한다. 수치는 전부 이 프로젝트에서 실측한 값이다.

---

## 1. 개요

### 1.1 제품 정의

**VoiceDesk**는 주제를 입력하면 ① Gemini가 대본을 쓰고 ② 사용자가 세그먼트 단위로 검토·수정한 뒤 ③ 로컬 TTS 엔진이 다화자 음성으로 렌더해 mp3·대본·타임스탬프·자막을 내보내는 **개인용 Windows 데스크톱 앱**이다. 주 용도는 외국어(영어) 듣기·말하기 학습 콘텐츠 제작이며, 한국어 합성과 학습 도구(속도 조절·구간 반복·발음 연습·Anki 내보내기)를 포함한다.

### 1.2 목표

- 주제 한 줄에서 완성된 다화자 오디오까지 **한 앱 안에서** 끝난다.
- 모든 추론은 **로컬**에서 돈다(대본 생성만 Gemini API). 렌더 산출물은 파일로 남는다.
- 대기가 긴 앱이므로 상태·진행·남은 시간이 항상 **숫자로** 보인다.
- 세그먼트(대본의 한 턴)가 편집·재생성·재생·연습·자막·카드의 **공통 단위**다.

### 1.3 비목표

- 상용 배포, 다중 사용자, 원격 접근(서버는 127.0.0.1 전용).
- 실시간 스트리밍 TTS 서비스(렌더 중 미리 듣기는 제공하나 저지연 보장은 없음).
- 음성 편집기(파형 컷·이펙트 편집 등).

### 1.4 용어

| 용어 | 정의 |
|---|---|
| 세그먼트 | 대본의 한 턴. `{speaker, text, note, translation}` |
| 화자 | `NARRATOR`, `A`~`D`. 엔진 렌더 시 보이스에 매핑된다 |
| 타이밍 | 세그먼트의 오디오 내 `[start, end)` 초 구간 |
| 엔진 | TTS 백엔드 구현. vibevoice / dia2 / supertonic |
| 잡(Job) | 백그라운드 작업 단위. 렌더·TTS·다운로드가 이 형태로 돈다 |

---

## 2. 시스템 요구환경

### 2.1 실행 환경

| 항목 | 요구 | 비고 |
|---|---|---|
| OS | Windows 11 | 실측: Education 26200 |
| GPU | 2.1.1 등급표 참조 (**최소 12GB · 전 기능 16GB · 한국어 전용은 GPU 불필요**) | **RTX 30 시리즈(Ampere) 이상** — 두 GPU 엔진이 bf16 고정이라 20 시리즈(Turing)는 미지원 |
| RAM | 16GB 이상 권장 | 모델 로드 버퍼 + Supertonic CPU 경로 |
| 디스크 | 모델 일습 약 16GB | 2.3 디렉터리 표준 참조 |
| Python | 3.11 (python.org) | `C:\ai\python311` — venv의 base 경로가 ASCII여야 함 |
| Node | 20+ | 프론트 빌드용 |
| Rust | stable | Tauri 빌드용 |
| WebView2 | Evergreen | Windows 11 기본 탑재 |

#### 2.1.1 GPU·VRAM 등급 (실측 기반)

GPU 엔진은 동시에 올라가지 않으므로(3.4) 요구 VRAM은 **가장 무거운 단일 조합**이 결정한다.
Windows 자체(WDDM·DWM 등)가 1~2.5GB를 상시 점유하므로 카드 총량이 아니라 가용량으로 계산할 것.

실측 점유(RTX 4090):

| 조합 | 상주 | 피크(프로세스) |
|---|---|---|
| Supertonic (한국어) | 0 GB — CPU 실행 | 0 GB |
| VibeVoice 1.5B (bf16) | 5.04 GB | 5.85 GB(단문) / 약 6.8 GB(6분30초 장문 — KV 캐시 증가) |
| Dia2 2B (CUDA 그래프) | 7.64 GB | 8.68 GB |
| Dia2 + 클로닝(whisper-large-v3 CUDA 상주) | 약 10.7 GB | 약 11~12 GB |

배포 사양 등급:

| VRAM | 판정 | 범위 |
|---|---|---|
| GPU 없음 | 가능 | 한국어(Supertonic)만 — CPU RTF 0.29로 실사용 무리 없음 |
| 8 GB | 조건부 | VibeVoice 단독·중간 길이까지. 장문은 데스크톱 점유에 따라 OOM 위험. Dia2 사실상 불가(피크 8.7) |
| **12 GB** | **최소 권장** | VibeVoice 전 범위 + Dia2 기본 모드(줄 단위). 클로닝은 아슬아슬 |
| **16 GB** | **전 기능 권장** | 클로닝 포함 전 기능 + 장문 여유 |
| 24 GB | 넉넉 | 개발 환경(실측 기준). 필수 아님 |

향후 여지: 12GB에서 클로닝을 지원하려면 whisper 전사를 CPU로 돌리는 옵션(전사 시간 증가, VRAM 약 3.5GB 절약)을 추가할 수 있다 — 현재 미구현.

### 2.2 금지·제약 (원 지침에서 계승)

1. WSL·Docker·conda 금지. python.org + venv만.
2. flash-attn 설치 시도 금지 → attention은 **PyTorch SDPA 고정**.
3. Linux 전용 패키지(triton, bitsandbytes, apex) 제외 → `torch.compile` 사용 불가.
4. torch는 CUDA 12.x Windows 휠을 **먼저** 설치하고 CPU판 덮어쓰기를 검증한다.
5. 코드·모델·캐시 경로에 한글·공백 금지 → 전부 `C:\ai` 아래. HF 캐시는 `HF_HOME=C:\ai\models\hf-cache`.
6. API 키는 Windows 자격 증명 관리자에만 저장. 코드·로그·설정 파일에 남기지 않는다.

### 2.3 디렉터리 표준

```
C:\ai\
├─ python311\                Python 3.11.9 본체
├─ models\
│  ├─ VibeVoice-1.5B\        5.04 GB (microsoft/VibeVoice-1.5B 공식 가중치)
│  ├─ Qwen2.5-1.5B\          토크나이저만
│  ├─ Dia2-2B\  mimi\        7.16 + 0.36 GB
│  ├─ supertonic-3\          0.38 GB (ONNX)
│  ├─ whisper\large-v3.pt    3.09 GB (클로닝 전사용)
│  └─ hf-cache\              HF_HOME
└─ voice-desk\               저장소 (github.com/hermits-diner/voice-desk)
   ├─ backend\               FastAPI + venv + 동봉 ffmpeg(bin\)
   ├─ app\                   Tauri 2 + React 18
   ├─ design\ docs\          문서
   └─ SETUP.md TESTING.md README.md
```

출력 기본 폴더는 `%USERPROFILE%\Music\VoiceDesk` (설정 변경 가능, 한글 경로 허용 — 파일 쓰기 전용이라 안전).

---

## 3. 아키텍처

### 3.1 구성

```
┌─ voice-desk.exe (Tauri 2 셸) ─────────────────────────────┐
│  WebView2 ── React 18 + TS + Tailwind 4 (화면 전부)        │
│  Rust 코어:                                               │
│    · 백엔드 스폰/종료 · Windows Job Object(동반 종료 보장)   │
│    · 포트 선점 검사(+10 폴백) · 커스텀 타이틀바 · 창 상태 기억 │
└───────────────┬───────────────────────────────────────────┘
                │ HTTP (127.0.0.1:7860~7870, CORS: localhost/tauri 한정)
┌───────────────▼───────────────────────────────────────────┐
│  python -m app.main  (FastAPI + uvicorn, 단일 프로세스)     │
│  ├─ jobs: 잡 레지스트리 + GPU_LOCK(직렬화) + PCM 스트림 버퍼 │
│  ├─ engines: manager ── vibevoice │ dia2 │ supertonic      │
│  ├─ audio: polish·익스팬더·loudnorm 2패스·인코딩·자막·컷    │
│  ├─ script_gen: Gemini(google-genai) 대본·줄 재생성·시리즈  │
│  ├─ downloads: 모델 다운로드 잡                             │
│  └─ secrets_store: Windows 자격 증명 관리자(keyring)        │
└───────┬───────────────────────┬───────────────────────────┘
   GPU(CUDA)                Gemini API (대본 생성만)
   VibeVoice·Dia2·whisper   
   CPU(onnxruntime): Supertonic
```

### 3.2 프로세스 수명주기 (필수 요구)

앱이 **어떤 방식으로 종료되든** 백엔드 파이썬은 함께 죽어야 한다 (GPU 메모리 5~8GB를 쥐고 있으므로).

- 정상 경로: `CloseRequested` → `Backend::stop()` (kill+wait) — 별도로 `POST /shutdown`도 제공.
- **비정상 경로: Windows Job Object.** 스폰 직후 자식을 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 잡에 배정한다. 앱이 `TerminateProcess`로 강제 종료돼도 커널이 파이썬 트리를 정리한다. **(실측 검증: 강제 종료 후 python 잔존 0, 포트 해제, VRAM 반환)**

### 3.3 포트 정책

기본 7860. 이 PC처럼 다른 프로그램(WSL 내 Gradio 앱)이 점유한 경우:

- **Rust**: 스폰 전에 `TcpListener::bind`로 7860→7870을 훑어 빈 포트를 골라 `--port`로 전달 → 프론트가 정확한 포트를 즉시 안다.
- **Python**(단독 실행 시): `--port` 명시가 없으면 같은 폴백을 수행하고 결과를 `settings.json`에 기록한다. `--port` 명시 시에는 폴백 없이 종료 코드 3.
- Vite 개발 포트는 6420/6421 (Hyper-V 예약 구간 1336–1435를 피함).

### 3.4 동시성 모델

- GPU 작업(렌더·TTS·미리듣기 생성)은 **`GPU_LOCK` 하나로 직렬화**한다. 초과 요청은 스레드가 락 대기 → 자연스러운 FIFO 큐가 된다 (배치 큐의 구현체).
- 다운로드 잡은 GPU를 쓰지 않으므로 락 없이 병렬.
- Supertonic은 CPU지만 단순화를 위해 같은 락을 쓴다(동시 합성 불필요).
- 엔진 상주: GPU 엔진은 한 번에 하나(전환 시 언로드+`empty_cache`), CPU 엔진(supertonic)은 별도 슬롯에 나란히 상주.

---

## 4. 기능 요구사항

| ID | 요구사항 | 구현 |
|---|---|---|
| FR-01 | 3단계 흐름: 주제 입력 → 대본 검토 → 렌더·다운로드, 스테퍼로 왕복 가능 | ✅ |
| FR-02 | 대본 생성: 주제·형식(4종)·길이(3종)·CEFR(A2~C1)·화자 수(1~4)·톤 → JSON 대본 | ✅ |
| FR-03 | 대본 JSON 파싱 실패 시 1회 재요청, 재실패 시 원문 표시 + 사용자 수정 진행 | ✅ |
| FR-04 | 세그먼트 단위 편집·삭제·순서 변경·단독 재생성·단독 미리듣기 | ✅ |
| FR-05 | 화자별 보이스 매핑·미리듣기(캐시)·교체 | ✅ |
| FR-06 | 렌더: 전체 진행률, (구간 단위 엔진은) 구간 진행률, 취소 | ✅ |
| FR-07 | 완료 화면: 실제 파형 + 세그먼트 경계 마커, 재생/구간 반복, 폴더 열기 | ✅ |
| FR-08 | 산출물: mp3(-16 LUFS) + 대본 txt + 타임스탬프 json + 자막 srt/vtt | ✅ |
| FR-09 | 빠른 변환 탭: 텍스트 → 단일 화자 TTS (엔진 선택 포함) | ✅ |
| FR-10 | 히스토리: 대본+mp3 한 항목, 어느 단계에서든 다시 열어 이어가기(재생 복원 포함) | ✅ |
| FR-11 | 설정: 키·모델·출력 폴더·포맷/비트레이트·엔진·포트·테마 + 엔진 세부 옵션 | ✅ |
| FR-12 | 첫 실행 온보딩: 키 → GPU/모델 확인(+인앱 다운로드) → 샘플 1회 | ✅ |
| FR-13 | 단축키: Ctrl+Enter 생성/렌더, Space 재생, Ctrl+S 폴더, Esc 설정 닫기 | ✅ |
| FR-14 | 오류 상태 화면: 서버 미기동·GPU 없음·모델 미설치·Gemini 키 오류·과부하 — 크래시 없이 원인+다음 행동 한 문장 | ✅ |
| FR-15 | 한국어 번역 병기: 세그먼트별 `translation` — 표시·txt·자막·Anki에만 쓰고 발화 금지 | ✅ |
| FR-16 | 렌더 중 이어 듣기: 합성된 부분부터 스트리밍 재생 | ✅ |
| FR-17 | 재생 속도 0.5~1.5× (음정 유지), 구간 LOOP | ✅ |
| FR-18 | 발음 연습: 구간 듣기(감속) → 마이크 녹음 → 비교 재생. 녹음 비저장 | ✅ |
| FR-19 | Anki 내보내기: 구간 오디오+문장+번역 카드 .apkg | ✅ |
| FR-20 | 시리즈: 이전 화 전체를 맥락으로 "다음 화" 대본 생성 | ✅ |
| FR-21 | 배치 큐: 렌더 중 추가 요청 자동 큐잉 + 진행 패널 | ✅ |
| FR-22 | Dia2 레퍼런스 클로닝: 화자별 wav(5~30초) 지정 → 그 목소리로 렌더 | ✅ |
| FR-23 | 부분 재렌더(실험): n번째 구간부터 재합성, 앞부분 재사용 + 크로스페이드 | ✅ 실험 표시 |
| FR-24 | 인앱 모델 다운로더: 온보딩·설정에서 가중치 내려받기 + 진행률 | ✅ |

### 비기능 요구사항

| ID | 요구사항 | 실측 |
|---|---|---|
| NFR-01 | 백엔드 기동(서버 응답까지) 3초 이내 | 0.47초 (torch 지연 임포트) |
| NFR-02 | 렌더 속도: 실시간 대비 1.2× 이내 | VV 0.73~0.81 · Dia2 0.76 · ST 0.29 |
| NFR-03 | 산출 오디오: 클리핑 0, NaN 0, -16±1 LUFS | 통과 |
| NFR-04 | 타임스탬프 연속성: 빈틈·역전 0, 총합=길이 | 통과 (자동 검사) |
| NFR-05 | 앱 강제 종료 시 백엔드 잔존 0 | 통과 (Job Object) |
| NFR-06 | 접근성: 전 조작 키보드, 포커스 링 상시, 본문 대비 4.5:1+ | DIRECTION.md 기준 구현 |
| NFR-07 | 비밀값이 디스크 평문·로그에 남지 않음 | keyring + redact() |

---

## 5. 백엔드 명세

### 5.1 API

Base: `http://127.0.0.1:{port}`. 모든 오류는 `{detail:{code, message[, raw]}}` 형태. `message`는 사용자에게 그대로 보여줄 한 문장.

| 메서드·경로 | 설명 | 비고 |
|---|---|---|
| GET `/` | 사람이 브라우저로 열었을 때 안내 JSON | |
| GET `/health` | 상태·엔진·VRAM·모델 설치·키 존재 | torch 미로드 시 nvidia-smi로 VRAM |
| GET `/voices` | 보이스 목록 (wav 프리셋 + `st-*` 스타일) | |
| GET `/voices/{id}/preview` | 보이스 샘플 mp3 | 최초 1회 합성 후 캐시. 렌더 중이면 409 |
| POST `/script` | ScriptRequest → 대본 JSON | 파싱 재시도 1회, 5xx 백오프 재시도 |
| POST `/script/segment` | `{script, index, model?}` → 한 줄 재작성 `{text, note, translation}` | 앞뒤 맥락 포함 |
| GET `/gemini/models` | generateContent 가능한 모델 목록 | 모델명 하드코딩 금지 원칙 |
| POST `/render` | RenderRequest → JobStatus(즉시) | 본문 5.3·5.4 |
| POST `/tts` | `{text, voice?, engine?}` → JobStatus | 빠른 변환·미리듣기 |
| GET `/jobs` | 최근 잡 목록 (큐 패널용) | |
| GET `/jobs/{id}` | 진행률·결과·오류 | 폴링 주기 0.7~1.5s |
| POST `/jobs/{id}/cancel` | 협조적 취소 | 엔진 루프가 플래그 확인 |
| GET `/jobs/{id}/audio` | 완성 오디오 파일 | |
| GET `/jobs/{id}/pcm?from_byte=` | 렌더 중 미리 듣기 int16 PCM 증분 | 헤더 X-Pcm-Total/-Sr/X-Job-State |
| GET `/audio?path=` | 히스토리 저장본 재생 | 출력 폴더 밖 접근 거부 |
| POST `/export/anki` | `{audio_path, title, timings}` → .apkg | ffmpeg 구간 컷 + genanki |
| POST `/models/download` | `{which}` → 다운로드 잡 | vibevoice·dia2·supertonic·whisper |
| GET/PUT `/settings` | 설정 조회·부분 갱신 | 갱신 시 엔진 재구성 |
| POST `/settings/gemini-key` | 키 저장(빈 값=삭제) | 응답은 존재 여부만 |
| POST `/cache/clear` | Dia2 구간 캐시 비우기 | |
| POST `/engine/unload` | GPU에서 엔진 내리기 | |
| POST `/shutdown` | 프로세스 종료 | sidecar 정리 경로 |

### 5.2 핵심 스키마

```jsonc
// Script (지침 고정 스키마 + translation 확장)
{ "title": str, "format": "Narration|Conversation|Interview|Monologue",
  "segments": [ { "speaker": "NARRATOR|A|B|C|D", "text": str,
                  "note": str|null,          // 연기 메모. 발화에 절대 넣지 않는다(5.4.5)
                  "translation": str|null } ] }

// RenderRequest
{ "script": Script, "engine": "vibevoice|dia2|supertonic"|null,
  "voices": [{"speaker","voice"}], "seed": int|null,
  "references": {"A": "C:\\...\\ref.wav"}|null,     // dia2 클로닝
  "resume_from": int|null, "prev_audio_path": str|null, "prev_timings": [...]|null }

// JobStatus (요약)
{ "id", "state": "queued|loading|running|encoding|done|error|cancelled",
  "progress": 0..1, "message", "elapsed", "eta",
  "segment_index"|null, "segment_total"|null,
  "audio_path","script_path","timing_path","duration","timings", "error_code","error" }
```

`ScriptRequest`는 `topic, format, length(short|medium|long→180/420/900단어), level(A2~C1), speakers(1~4), tone, translate(기본 true), previous(Script|null — 시리즈)`.

### 5.3 잡 모델

- `Job`: 상태 머신 + 진행률(`report(done_s, total_s, msg)` → ETA 계산) + 협조적 취소(Event) + **PCM 버퍼**(`push_pcm(chunk|None, sr)` — None은 재시드 리셋 신호, int16로 축적, `read_pcm(from)`으로 증분 반환).
- `jobs.run(job, fn)`: 데몬 스레드에서 `GPU_LOCK`을 잡고 실행. `EngineError`는 코드·문장 그대로, 그 외 예외는 `redact()` 후 400자 제한으로 기록.
- 레지스트리는 최근 50건 유지.

### 5.4 엔진 계층

#### 5.4.1 공통 인터페이스

```python
class Engine(Protocol):
    name: str;  loaded: bool
    def load(self) / unload(self)
    def render(script, voice_map, *, on_progress, should_cancel,
               seed=None, on_audio=None, **엔진별) -> RenderResult
# RenderResult: audio(f32 mono), sample_rate, timings[SegmentTiming],
#               timings_estimated, notes[str]
```

`on_audio(chunk, sr)`는 합성 즉시 호출되는 스트리밍 훅(FR-16). 매니저(`EngineManager`)는 GPU 슬롯 1 + CPU 슬롯 dict를 관리하고, 설정 변경 시 전부 버려 재구성한다. torch·엔진 모듈은 **지연 임포트**(기동 0.47초의 핵심).

#### 5.4.2 VibeVoice 1.5B (기본, 영어·중국어)

- 코드: `vibevoice-community/VibeVoice@952326dd` (공식 저장소는 TTS 추론 코드를 제거함 — ADR-1). 가중치: 공식 `microsoft/VibeVoice-1.5B`. `--no-deps` 설치로 transformers 4.51.3 핀 유지.
- 입력 변환: 대본 → `"Speaker N: 텍스트"` 멀티라인(화자 등장순 1~4). bf16, `attn_implementation="sdpa"`, `set_ddpm_inference_steps(10)`, `cfg_scale 1.3`, `do_sample=False`, 보이스는 레퍼런스 wav 프리필.
- **조기 EOS 방어**: 확산 헤드 노이즈가 LLM에 되먹임되어 드물게 대본을 건너뛴다(410단어→50초 실측). 시드 고정(기본 1234) + 출력 검증(단어수/길이 > 4.5단어/초 = 절단) + 재시드 7919·k 재시도 2회.
- **타임스탬프**(`timing.py`): 생성 토큰 열에서 ①확산 토큰 1개=정확히 3200샘플(예외 없음) ②`speech_end` 마커 위치는 정확하나 개수는 턴 수와 불일치할 수 있음(같은 화자 연속·3인 이상이면 병합) → END를 앵커로 예상 경계에 배정하고, 앵커 없는 경계는 예상 위치 ±0.45초에서 가장 조용한 20ms로 스냅. 품질은 `timing_notes`로 산출물에 기록.
- **후처리**: 조용한 구간에 붙는 2~5.6kHz 금속성 잔향(모델 아티팩트, ddpm 스텝·보이스로 제거 불가) → 꼬리 트림+80ms 페이드(`audio.polish`) + 인코딩 시 다운워드 익스팬더(5.5). 설정 `vv_polish`.

#### 5.4.3 Dia2 2B (보조, 영어 2인)

- 코드·가중치: `nari-labs/dia2` + `Dia2-2B` + `kyutai/mimi`. 대본 형식 `[S1]/[S2]`, 컨텍스트 상한 1500스텝@12.5Hz=120초.
- **기본 모드 = 줄 단위 합성**: 줄마다 생성 → 내용 해시(v2) 캐시 → 무음 삽입(화자 전환 0.5s, 동일 화자 0.8s). 한 줄만 고치면 그 줄만 재합성(실측 25.2s→3.3s). 타이밍은 정확.
- **`use_cuda_graph=True` 필수**: Windows WDDM 커널 런치 오버헤드로 끄면 RTF 4.87, 켜면 0.76 (6.4×).
- **발산 방어**: 샘플링(temp 0.8)이라 드물게 클리핑 굉음(실측 피크 1.0, 27,693클립) → 피크·클리핑률·RMS 검사(`AudioQc.degenerate`) + 재시드 재시도 2회.
- **클로닝 모드**(`references` 지정 시): 줄 단위 대신 **90초 이하 턴 묶음**으로 렌더(프리픽스 전사 비용 때문), `prefix_speaker_1/2`에 레퍼런스 전달. 레퍼런스는 사전에 24kHz 모노 리샘플(내부 선형 보간 폴백 회피), 30초 초과 컷. whisper-large-v3 전사는 `wts.load_model`을 lru_cache로 감싸 프로세스당 1회 로드. 묶음 내부 타이밍은 무음 정렬 추정으로 표시.
- 비언어 태그: note가 알려진 태그(laughs, sighs, coughs 등 화이트리스트)일 때만 `(tag)`로 전달. 서술형 노트는 그대로 읽히므로 제외(ADR-6).

#### 5.4.4 Supertonic 3 (한국어·다국어, CPU)

- `Supertone/supertonic` v3 — 99M ONNX, MIT, `pip install supertonic`(onnxruntime만 추가되어 기존 핀과 무충돌). 모델 385MB, 44.1kHz, 보이스 스타일 F1~F5·M1~M5(id `st-*`).
- 세그먼트 단위 합성+무음 삽입(Dia2와 동일 구조) → 타이밍 정확. `lang`(기본 ko)·`speed`(1.05)·`total_steps`(8)는 설정.
- **한국어 검증(채택 조건)**: whisper-large-v3 재전사 CER — 실제 발음 오류 ≈ 0%(표면 오류는 전부 "구월 일일"↔"9월 1일"류 표기 차이), 아라비아 숫자·금액·날짜 낭독 정확. **약점: 전화번호식 숫자열(010-…)**. 상세는 `backend/verify_korean.py`.
- CPU 실행이므로 GPU 엔진을 내리지 않고 상주(매니저 CPU 슬롯).

#### 5.4.5 노트(연기 메모) 처리 규칙

`note`는 **어떤 엔진에서도 발화 텍스트에 넣지 않는다.** VibeVoice는 괄호 지시를 감정으로 해석하지 않고 그대로 읽는다는 것이 실사용에서 확인됐다(ADR-6). 노트의 용도: 화면 표시, Gemini 줄 재생성 맥락, (Dia2 한정) 비언어 태그 화이트리스트 통과 시 소리.

### 5.5 오디오 파이프라인

```
엔진 f32 PCM ─ polish(VV만: 꼬리 트림+페이드) ─ tmp wav
  ─ ffmpeg(동봉 9.0.1): [expander(VV만)] → loudnorm 2패스 → mp3/wav
  ─ 대본 txt · 타임스탬프 json · srt(BOM)/vtt · (요청 시) Anki apkg
```

- **loudnorm 2패스**: 1패스로 측정(익스팬더 적용 시 같은 체인으로 측정) 후 linear 모드 정규화 I=-16, TP=-1.5, LRA=11. `-ar`로 엔진 고유 샘플레이트 유지(loudnorm의 192kHz 내부 처리가 48kHz로 뱉는 것 방지).
- **다운워드 익스팬더**(compand): -30dBFS 이상 무변화 / -42dBFS→-52 / 이하 1.4:1. 발화 평균 -16.0 LUFS 유지, 구절 사이 잔향 -79.8→-124.3dBFS(실측).
- 파일명: `YYYYMMDD_제목_형식.ext`, Windows 금지 문자 제거, 중복 시 ` (n)`. **확장자는 문자열 결합으로 붙인다**(제목 마침표 + `with_suffix` 버그, ADR-7).
- srt: 번역이 있으면 둘째 줄. BOM 포함(플레이어 호환).
- Anki: 세그먼트별 mp3 컷(재인코딩, 0.2초 미만 제외) + genanki 모델(앞면 오디오/뒷면 문장+번역), 덱 id는 제목 해시.

### 5.6 대본 생성 (Gemini)

- `google-genai` SDK, `response_schema`로 JSON 강제. 시스템 프롬프트 원칙: 낭독 가능한 산문만, 숫자·기호는 읽는 대로, 지시는 note로 분리, 번역은 translation으로.
- 모델: 설정값(기본 `gemini-3.6-flash` — 실측에서 3.7은 지속 503). 목록은 `/gemini/models`로 동적 조회, 하드코딩 금지.
- 재시도: 파싱 실패 1회 재요청(지침), **일시 오류(503/500/타임아웃)는 1.5→4→8초 백오프 3회**. 오류는 코드별 한 문장으로 매핑(bad_key/bad_model/quota/busy/parse), 원본 JSON을 사용자에게 노출하지 않는다.
- 시리즈: `previous` 대본 전문을 프롬프트에 포함, "같은 인물·설정으로 이어서, 반복하지 말 것".
- 줄 재생성: 전체 대본을 번호 붙여 보여주고 해당 줄만 재작성(±길이 유지), translation 포함 반환.

### 5.7 비밀값

`keyring`(WinVaultKeyring) 서비스명 `voice-desk`. 저장·삭제·존재 확인만 노출하고 값은 API로 내보내지 않는다. 예외 메시지는 `redact()`가 알려진 비밀값을 `***`로 치환한 뒤 기록한다.

### 5.8 모델 다운로드

`app/downloads.py` 카탈로그(대상·repo·크기): vibevoice(5.1GB, +Qwen 토크나이저) / dia2(7.6GB, +mimi) / supertonic(0.4GB, SDK 다운로더 위임) / whisper(3.1GB, openai CDN). HF `snapshot_download` 이어받기 + 8회 재시도. 진행률은 디스크 바이트/기대 크기, 잡으로 노출.

---

## 6. 프론트엔드 명세

### 6.1 화면 구조

```
타이틀바(32px, 커스텀) ─ [빠른 변환] [설정] [─ □ ✕]
├ 히스토리 사이드바 260px (접으면 44px)
├ 메인: 스테퍼(01 주제 / 02 대본 / 03 렌더) + 단계 화면
│   또는 온보딩 / 빠른 변환 / 백엔드 오류 전체 화면
└ 트랜스포트 바(44px, 상시) ─ 램프·진행/재생·속도·이어듣기·ENGINE·VRAM
우하단 QUEUE 패널(배치 잡 있을 때) · 발음 연습 다이얼로그 · 설정 패널(우측 시트)
```

단계 화면 요지 — **①주제**: 폼+Ctrl+Enter, 키 없음/오류 인라인 안내, 파싱 실패 시 원문 편집 진행. **②대본**: 세그먼트 레일(시그니처 — 카드 높이에 정렬된 타임라인, DIRECTION.md 6절) + 카드(화자 셀렉트·본문·노트·번역·단어 수·호버 액션 5종) + 보이스 바(엔진별 필터, 미리듣기, Dia2 클로닝 지정) + 엔진 셀렉트. **③렌더**: 파형(렌더 중 진행 띠 → 완료 후 실제 피크+경계 마커), 레일 순차 점등(구간 보고 엔진은 실측, VibeVoice는 단어 가중 추정), 구간 행(타임코드·LOOP·연습·여기부터 다시), 완료 바(다음 화·Anki·대본 고치기·폴더 열기).

### 6.2 상태·재생

- 백엔드 연결: Tauri 이벤트(`backend-ready/-failed`) + `backend_status` 폴백, 120초 대기(경과 초 표시), 실패 시 로그 접이식 오류 화면.
- 헬스 폴링: 유휴 8s / 작업 중 2s. **의존성은 busy 불리언만**(job 객체를 걸면 인터벌이 리셋되어 영원히 발화하지 않는다 — 실측 버그).
- 완성 재생: 단일 `HTMLAudioElement`. `playbackRate`+`defaultPlaybackRate`로 속도(음정 유지), timeupdate에서 LOOP 구간 되감기. 파형 피크는 fetch+WebAudio decode(900버킷).
- 이어 듣기(`LivePlayer`): 700ms마다 `/pcm` 증분 → AudioBuffer 이어 스케줄. total 감소=재시드 리셋. 탐색 없음, 완료 시 잔여 스케줄 후 자동 정지.
- 히스토리: `localStorage["voicedesk.history.v1"]`, 항목 `{id, createdAt, title, format, engine, script, voices, audioPath, timingPath, duration, timings, step}` 최대 200. 열기 시 step 복원, 렌더 완료 항목은 가짜 done 잡+`/audio`로 재생까지 복원.

### 6.3 단축키

| 키 | 동작 |
|---|---|
| Ctrl+Enter | 1단계: 대본 만들기 / 2단계: 음성 만들기 |
| Space | 재생·정지 (입력 필드 밖) |
| Ctrl+S | 저장 폴더 열기 |
| Esc | 설정 닫기 |

---

## 7. 디자인 시스템 (규범: `design/DIRECTION.md`)

무드 **Instrument · Legible · Unlit**. 요지만 발췌 — 구현 시 DIRECTION.md가 우선한다.

- 서피스: 온도 있는 중성색(R>G>B) `#171614 / #201E1B / #2A2724`, 라인 `#38342F`. 다크 기본 + 라이트 세트. 그림자는 다크에서 금지.
- **램프 3색이 곧 상태 체계**: signal `#E2A356`(텅스텐 앰버 — 유일한 강조색), ready `#6FA287`, clip `#CF6055`.
- **앰버 규율**: 신호가 있을 때만(생성 중 파형·재생 헤드·활성 스텝·포커스 링·연기 메모). 버튼·로고·탭 등 정적 크롬 금지.
- 타입 5단계: Pretendard(본문·UI) + IBM Plex Mono(계측·실크스크린 legend, tabular-nums). **legend의 0.14em 자간은 라틴 전용** — 한글 라벨은 자간 0의 `t-label`.
- 라운딩 3/6px, 행높이 32px 격자, 모션은 120~200ms 상태 전환 + 파형 성장·레일 점등만. 스피너·스켈레톤 금지 — 대기는 숫자로.

---

## 8. 산출물 명세

렌더 1회 → 같은 폴더에:

| 파일 | 내용 |
|---|---|
| `.mp3`(또는 wav) | -16 LUFS, TP -1.5, 엔진 샘플레이트(24k/44.1k), 기본 128kbps |
| `.txt` | `[화자] 원문` + 들여쓴 번역 |
| `.json` | `{title, format, engine, sample_rate, duration, timings_estimated, timing_notes[], segments[{index, speaker, text, translation, start, end}]}` |
| `.srt` / `.vtt` | 구간=자막 1개, 번역 둘째 줄, srt는 BOM |
| `.apkg` | (버튼 시) 구간 오디오 카드 덱 |

`timing_notes`는 경계 산출 품질을 사람 문장으로 기록한다 (예: "세그먼트 경계: 9개 정확, 4개 무음 정렬.") — 숨은 실패 방지 장치.

---

## 9. 성능 실측 및 수용 기준

### 9.1 실측 (RTX 4090, Windows 11)

| 항목 | 값 |
|---|---|
| 백엔드 기동 → /health | 0.47초 |
| VibeVoice 로드 / 상주 / 피크 | 5.7s / 5.04GB / 5.85GB |
| VibeVoice RTF | 0.73~0.81 (6분25초·1,208단어를 280초) |
| Dia2 로드 후 상주 / RTF | 7.64GB / 0.76 (CUDA 그래프. 끄면 4.87) |
| Dia2 한 줄 수정 재렌더 | 25.2s → 3.3s (캐시) |
| Supertonic RTF (CPU) | 0.29 · VRAM 0 |
| 보이스 미리듣기 | 첫 2.5s → 캐시 0.01s |
| Gemini 대본(420단어) | 모델 상태에 따라 8~40s (+503 백오프) |

### 9.2 수용 테스트

`TESTING.md`가 정본. 핵심: 같은 주제 Narration+3인 Conversation 산출물 5종 생성·연속성 검사, 5분+ 대화 화자 유지(청취), Dia2 줄 캐시, 강제 종료 동반 정리, 오류 5상태 무크래시, 확장 기능 15항목 체크리스트, 자동 회귀는 `backend/test_e2e.py`·`test_dia2_cache.py`·`test_features.py`·`verify_korean.py`.

---

## 10. 제약 및 알려진 이슈

| 이슈 | 상태·대응 |
|---|---|
| VibeVoice 조기 EOS(대본 건너뜀) | 시드 고정+단어/초 검증+재시드로 방어. 근본 원인은 모델 |
| VibeVoice 금속성 잔향 | 원천 제거 불가(SDPA 제약으로 flash-attn 비교도 불가). 익스팬더+트림으로 완화, `vv_polish`로 토글 |
| VibeVoice 턴 경계 마커 불완전 | 같은 화자 연속·3인 이상에서 병합 → 앵커+무음 스냅, 품질을 json에 명시 |
| Dia2 발산 출력 | QC+재시드. 지속 시 사용자 안내 |
| Supertonic 전화번호식 숫자열 | 부정확. 문서·힌트로 안내 |
| 부분 재렌더 이음새 | 목소리 톤이 미세하게 튈 수 있음 — 실험 표시 유지 |
| VibeVoice 한국어 | 미검증 교차언어 전이라 미지원(한국어는 Supertonic 사용) |
| 발음 연습 마이크 | WebView2 권한 거부 환경에서 안내 문구로 처리 |
| 포트 7860 | 이 PC는 WSL Gradio 앱이 점유 — 자동 폴백으로 해소 |

---

## 11. 보안·프라이버시

- 수신 주소 127.0.0.1 고정, CORS는 localhost/127.0.0.1/tauri.localhost 한정.
- 파일 서빙(`/audio`)은 출력 폴더 내부만. 경로는 resolve 후 부모 검사.
- 비밀값: 자격 증명 관리자 단일 저장, redact 이중 방어. `settings.json`에는 비밀값 없음.
- 외부 통신: Gemini API(대본), HuggingFace/openai CDN(모델 다운로드)뿐. TTS 추론·오디오는 전부 로컬.
- 서드파티 코드: 고정 커밋 + 설치 전 정적 검사(네트워크·exec·pickle 부재 확인, SETUP.md 2절). 사용자 `.pt` 로드 금지(wav만).

---

## 12. 빌드·설치

- 개발: `backend` venv 구성(SETUP.md 8절) 후 `npm run tauri dev`. 백엔드는 앱이 스폰.
- 배포: `npm run tauri build` → NSIS `VoiceDesk_0.1.0_x64-setup.exe`(앱 셸만, 3.7MB, currentUser). 백엔드·모델은 `C:\ai` 표준 배치를 전제(1.3 비목표 참조).
- 클린 PC 검증 절차: `TESTING.md` A·B절.

---

## 부록 A. 주요 결정 기록 (ADR 요약)

| # | 결정 | 근거 |
|---|---|---|
| 1 | VibeVoice 추론 코드는 커뮤니티 포크(고정 커밋) | MS가 공식 저장소에서 TTS 추론을 제거("Disabled due to widespread misuse"). 가중치는 공식 유지. 설치 전 정적 검사 수행 |
| 2 | 한 venv에 두 GPU 엔진 공존(`--no-deps`) | transformers 핀 충돌(4.51.3 vs ≥4.55.3)이지만 Dia2 실사용 심볼 3개가 4.51.3에 존재. venv 분리는 sidecar 구조와 상충 |
| 3 | Dia2 기본 모드 = 줄 단위 + 해시 캐시 | "수정 줄만 재합성" 요구를 캐시 단위=줄로 충족. 대가로 턴 간 억양 연결 포기(클로닝 모드는 묶음 단위) |
| 4 | 타임스탬프 = 토큰 앵커 + 무음 스냅 | 확산토큰=3200샘플은 무결, END 개수는 불완전 → 정확한 것만 앵커로 쓰고 품질을 산출물에 명시 |
| 5 | 한국어 엔진 = Supertonic 3 | "검증된 것만" 지시 → whisper 재전사 CER로 객관 검증 통과. ONNX/CPU라 의존성·VRAM 무부담. CosyVoice는 pynini(Windows 불가) 리스크, MeloTTS는 transformers 핀 충돌 |
| 6 | 노트를 발화에 넣지 않음 | 괄호 지시를 모델이 그대로 읽는 것을 사용자가 확인. 지침의 "괄호 지시" 방식은 이 모델에서 무효 판정 |
| 7 | 확장자는 문자열 결합 | 제목의 마침표가 `with_suffix` 기준점을 오염(자막 누락 실측) |
| 8 | 렌더 중 미리 듣기 = 증분 PCM 폴링 + WebAudio | 청크 WAV 스트리밍·웹소켓 대비 단순, 재시드 리셋을 total 감소로 자연 전파 |
