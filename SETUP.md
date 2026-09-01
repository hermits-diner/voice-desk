# VoiceDesk — 셋업 기록

Windows 11 · RTX 4090 24GB 환경. WSL · Docker · conda 미사용.
마지막 갱신: 2026-09-01 (1 · 2단계 완료 시점)

---

## 0. 경로 결정

지침의 "경로에 한글 · 공백 금지" 제약 때문에 **프로젝트 전체를 `C:\ai\voice-desk` 로 옮겼습니다.**
원래 작업 폴더 `C:\Users\오정훈\Desktop\MySpeak` 는 한글이 포함돼 있어 torch 확장 빌드,
HuggingFace 캐시, ffmpeg subprocess 호출에서 인코딩 문제를 일으킬 수 있습니다.

같은 이유로 아래 두 가지도 한글 경로 밖으로 뺐습니다.

| 대상 | 기본 위치 | 실제 위치 |
|---|---|---|
| Python 3.11 본체 | `%LOCALAPPDATA%\Programs\Python` | `C:\ai\python311` |
| HuggingFace 캐시 | `C:\Users\오정훈\.cache\huggingface` | `C:\ai\models\hf-cache` (`HF_HOME`) |

venv 의 `pyvenv.cfg` 가 base 인터프리터 경로를 그대로 참조하기 때문에 Python 본체까지 옮겼습니다.

```
C:\ai\
├─ python311\                 3.11.9 (python.org, 사용자 단위 무인 설치)
├─ models\
│  ├─ VibeVoice-1.5B\         5.04 GB   microsoft/VibeVoice-1.5B (공식 가중치)
│  ├─ Qwen2.5-1.5B\           0.01 GB   토크나이저 파일만
│  ├─ Dia2-2B\                7.16 GB   nari-labs/Dia2-2B
│  ├─ mimi\                   0.36 GB   kyutai/mimi 코덱
│  └─ hf-cache\               HF_HOME
└─ voice-desk\
   ├─ backend\
   │  ├─ .venv\
   │  ├─ bin\                 ffmpeg.exe / ffprobe.exe (정적)
   │  ├─ third_party\
   │  │  ├─ VibeVoice\        커뮤니티 포크 @952326dd
   │  │  └─ dia2\             nari-labs/dia2 @8687268f
   │  └─ outputs\             검증 산출물
   ├─ app\                    (Tauri, 미착수)
   └─ design\DIRECTION.md
```

---

## 1. 버전 표

### 기반

| 항목 | 버전 | 비고 |
|---|---|---|
| OS | Windows 11 Education 26200 | |
| GPU | RTX 4090 24GB · sm_89 | 드라이버 596.49 (CUDA 13.2) |
| Python | 3.11.9 | python.org 무인 설치, `C:\ai\python311` |
| Rust / Cargo | 1.97.1 | Tauri 빌드용, 기존 설치 사용 |
| Node / npm | 24.19.0 / 11.17.0 | `C:\Program Files\nodejs`, PATH 미등록 |
| MSVC Build Tools | 2022 | 기존 설치 |
| WebView2 | 151.0.4129.107 | 기존 설치 |
| ffmpeg | 9.0.1 essentials (gyan.dev) | `backend\bin` 에 동봉 |

### 핵심 패키지

| 패키지 | 버전 | 선택 이유 |
|---|---|---|
| torch | **2.9.1+cu126** | CUDA 12.x Windows 휠 요구. cu126 는 cp311 휠이 2.13까지 있으나, transformers 4.51.3 과의 검증 이력을 고려해 2.9.1 채택 |
| torchaudio | 2.9.1+cu126 | torch 와 동일 채널 |
| transformers | **4.51.3** | VibeVoice 가 이 버전에 고정. 아래 "충돌 해소" 참조 |
| accelerate | 1.6.0 | VibeVoice 포크 핀 |
| diffusers | 0.39.0 | |
| numpy | 2.2.6 | numba 0.67 호환 상한 |
| librosa | 0.11.0 | 레퍼런스 보이스 로드 · 리샘플 |
| soundfile | 0.14.0 | wav I/O |
| sphn | 0.2.1 | Dia2 오디오 I/O. cp311 win_amd64 휠 존재 |
| safetensors | 0.8.0 | Dia2 는 `==0.5.3` 을 핀하지만 `safe_open` 만 쓰므로 상위 버전으로 통일 |
| vibevoice | 0.1.0 (@952326dd) | 커뮤니티 포크, editable |
| dia2 | 0.1.0 (@8687268f) | 공식 저장소, editable |

**torch 가 CPU 판으로 덮이지 않았는지 확인 완료:** `torch 2.9.1+cu126 / cuda 12.6 / is_available True`

전체 목록은 `backend\requirements.lock.txt` 참조.

---

## 2. VibeVoice 추론 코드 — 왜 커뮤니티 포크인가

**공식 `microsoft/VibeVoice` 저장소에서 TTS 추론 코드가 제거되었습니다.**
`docs/vibevoice-tts.md` 의 "Installation and Usage" 섹션이 통째로
*"Disabled due to widespread misuse."* 한 줄로 대체돼 있습니다.

| | 공식 (`@94da20d9`) | 커뮤니티 포크 (`@952326dd`) |
|---|---|---|
| `modeling_vibevoice_inference.py` | **없음** | 있음 |
| `demo/inference_from_file.py` | **없음** | 있음 |
| 레퍼런스 보이스 wav | **없음** | 9종 (en 5 · zh 3 · in 1) |
| `__init__.py` 노출 | Streaming 전용 | TTS + Streaming |

공식에 남은 `VibeVoiceForConditionalGeneration` 은 학습용 `forward` 만 있고
diffusion head 샘플링 루프가 없어 그대로는 음성을 만들 수 없습니다.

**가중치는 공식 것을 그대로 씁니다.** HuggingFace `microsoft/VibeVoice-1.5B` 는
정상 공개 상태이며(2026-01-22 갱신, gated 아님) 다른 TTS 모델로 대체하지 않았습니다.
바뀐 것은 로더 · 추론 코드뿐입니다.

### 포크 실사 기록

```
vibevoice-community/VibeVoice
  fork 플래그 : false (독립 repo)
  생성        : 2025-09-04   (MS 가 원본을 내린 직후)
  고정 커밋   : 952326ddb264062466a888cf32a5b2f4e803e16e (2026-08-29)
  ★ 1,557   fork 721   MIT
```

설치 전 정적 검사를 돌렸고 아래를 확인했습니다.

- `eval(` / `exec(` / `__import__` / `subprocess` / `os.system` / 소켓 / HTTP 호출 **없음**
  (검출된 `eval` 은 전부 `nn.Module.eval()` 평가 모드)
- 하드코딩된 외부 URL 은 전부 논문 · 문서 인용 (arxiv, huggingface papers, apache license)
- `base64.b64decode` / `pickle.loads` / `marshal.loads` **없음**
- `setup.py` 없음 (pyproject 만) → 설치 시 실행되는 커스텀 빌드 훅 없음
- `torch.load` 는 전부 로컬 체크포인트용. `weights_only=False` 는
  `demo/streaming_inference_from_file.py` 한 곳뿐이며 이 앱은 그 경로를 쓰지 않음

**운영 규칙:** 사용자가 올린 `.pt` 파일을 로드해야 할 일이 생기면 반드시
`weights_only=True` 를 명시합니다. 보이스는 `.wav` 경로만 사용합니다.

---

## 3. 의존성 충돌 해소

VibeVoice 와 Dia2 의 선언이 정면 충돌합니다.

| | VibeVoice 포크 | Dia2 |
|---|---|---|
| transformers | `==4.51.3` | `>=4.55.3` |
| safetensors | (핀 없음) | `==0.5.3` |

**한 venv 로 해결했습니다.** Dia2 가 transformers 에서 실제로 쓰는 심볼은
`MimiModel`, `AutoTokenizer`, `PreTrainedTokenizerBase` 세 개뿐이고 전부 4.51.3 에 존재합니다
(`MimiModel` 은 4.45 부터 포함). safetensors 는 `safe_open` 만 쓰므로 0.8.0 에서 문제없습니다.

따라서 두 패키지를 **`pip install --no-deps -e`** 로 설치해 선언 핀이 환경을 흔들지 않게 했습니다.
import 검증까지 통과했습니다.

```
torch 2.9.1+cu126 | transformers 4.51.3 | safetensors 0.8.0 | numpy 2.2.6 | cuda True
MimiModel ok / dia2 import ok / VibeVoiceForConditionalGenerationInference ok
```

venv 를 두 개로 쪼개는 안은 채택하지 않았습니다. sidecar 프로세스가 둘로 늘고
엔진 전환 때 프로세스를 갈아야 해서 지침의 "모델 상주 · 전환 시 교체" 구조와 어긋납니다.

---

## 4. 제외한 패키지와 사유

### Linux 전용 / 설치 금지

| 패키지 | 사유 |
|---|---|
| `flash-attn` | 지침상 설치 시도 금지. eager + PyTorch SDPA 로 대체. RTX 4090 에서 `flash_sdp_enabled=True`, `mem_efficient_sdp_enabled=True` 확인 |
| `triton` | Linux 전용. Windows 포크(`triton-windows`)가 존재하지만 지침이 제외를 명시. 결과적으로 `torch.compile` 경로를 쓰지 않음 |
| `bitsandbytes` | Linux 전용. 양자화를 쓰지 않으므로 불필요 |
| `apex` | Linux · 소스 빌드 전용. VibeVoice 가 `try/except` 로 감싸 두었고, 없으면 네이티브 RMSNorm 으로 폴백. 실행 시 `APEX FusedRMSNorm not available, using native implementation` 로그가 정상적으로 뜸 |
| `vllm` | 공식 저장소의 `vllm_plugin` 은 Linux 서빙용. 이 앱은 로컬 단일 프로세스 |

### 불필요해서 제외

| 패키지 | 사유 |
|---|---|
| `gradio` | 양쪽 저장소가 데모 UI 용으로 요구. 프론트엔드는 Tauri 이므로 불필요 (포크는 `==5.50.0` 을 핀해 무겁기까지 함) |
| `aiortc` · `av` | VibeVoice 실시간 · 영상 데모 전용 |
| `datasets` · `peft` | VibeVoice 파인튜닝 전용. 추론 경로에서 import 되지 않음 |
| `resampy` | `librosa` 가 리샘플을 담당하므로 중복 |
| `whisper-timestamped` | Dia2 레퍼런스 클로닝에서만 지연 import. openai-whisper + whisper-large-v3(약 3GB)를 추가로 끌어옴. **클로닝 기능을 확정할 때 설치 예정 — 현재 미설치** |
| `hf_xet` | HF 다운로드 가속용. 없으면 일반 HTTP 로 폴백되며 정상 동작 |

---

## 5. 알려진 이슈와 대응

### 5-1. `sphn.read_wav` 부재

Dia2 의 `runtime/audio_io.py` 가 `sphn.read_wav` 를 호출하지만 sphn 0.2.1 의 공개 API 는
`read` / `read_opus` / `write_wav` / `resample` 뿐입니다. 다행히 호출부가
`try/except` 로 감싸 `soundfile` 로 폴백하고, `resample_audio` 도 `hasattr` 가드가 있어
**코드 수정 없이 동작합니다.**

다만 폴백 리샘플러(`_resample_linear`)가 선형 보간이라 품질이 낮습니다.
→ **레퍼런스 오디오는 백엔드에서 미리 24kHz 로 맞춰 넣습니다.**

### 5-2. Dia2 는 CUDA 그래프 없이는 4배 느립니다

Windows 의 WDDM 드라이버 모델에서 커널 런치 오버헤드가 지배적입니다.
Dia2 는 스텝마다 depformer 로 32개 코드북을 도는 구조라 여기에 특히 취약합니다.

동일 대본 · 동일 시드 측정:

| | 생성 시간 | RTF |
|---|---|---|
| CUDA 그래프 끔 | 130.4s | 4.87 |
| CUDA 그래프 켬 | **19.1s** | **0.761** |

→ **Dia2 는 `use_cuda_graph=True` 를 기본값으로 둡니다.** (`--torch-compile` 은 triton 이 없어 사용 불가)

### 5-3. Dia2 출력이 가끔 발산합니다

temperature 0.8 · top_k 50 샘플링이라 같은 대본에서도 시드에 따라 결과가 크게 다릅니다.
비언어 표기 대본으로 3개 시드를 돌린 결과:

| 시드 | 피크 | RMS | 클리핑 샘플 |
|---|---|---|---|
| 1234 | 1.0000 | −6.3 dBFS | **27,693** ← 발산 |
| 7 | 0.7445 | −18.6 dBFS | 0 |
| 99 | 0.8492 | −23.3 dBFS | 0 |

태그 때문이 아니라 샘플링 운입니다. → **백엔드에 출력 검증(피크 · 클리핑 비율 · RMS)과
자동 재시드 재시도를 넣습니다.** VibeVoice 는 `do_sample=False` 결정론적 생성이라 해당 없음.

### 5-4. SDPA 음질은 청취 확인 대기

포크의 `inference_from_file.py` 는 CUDA 에서 `flash_attention_2` 를 기본으로 쓰고,
SDPA 폴백 시 *"only flash_attention_2 has been fully tested, and using SDPA may result in
lower audio quality"* 라고 경고합니다. flash-attn 설치가 금지돼 있으므로 SDPA 로 고정했고,
계측상 이상(NaN · 클리핑 · 무음)은 없습니다. **최종 판단은 청취 결과에 따릅니다.**

### 5-5. ffmpeg loudnorm 이 48kHz 로 업샘플합니다

`loudnorm` 필터는 내부적으로 192kHz 로 올린 뒤 출력하므로 24kHz 소스가 48kHz mp3 로 나옵니다.
대역폭상 얻는 것 없이 비트레이트만 낭비하므로 **`-ar 24000` 을 명시**합니다.

### 5-6. VibeVoice 의 턴 경계 마커는 항상 나오지 않습니다

세그먼트 타임스탬프 json 을 만들려면 대본 턴이 오디오의 몇 초에 해당하는지 알아야 합니다.
VibeVoice 는 대본 전체를 한 번에 렌더하므로 이 정보를 따로 얻어야 합니다.

측정으로 확인한 것:

| 사실 | 신뢰도 |
|---|---|
| 확산 토큰(`<\|vision_pad\|>`) 1개 == 정확히 3200 샘플 | **예외 없음.** 시험한 모든 경우에서 오차 0 |
| `speech_end`(`<\|vision_end\|>`) 가 찍힌 **위치**는 정확한 발화 경계 | 정확 |
| `speech_end` 의 **개수**가 대본 턴 수와 같다 | **아니오** |

턴 수 대비 END 마커 개수:

| 대본 | 턴 | END | 결과 |
|---|---|---|---|
| 2인 교대 4턴 | 4 | 4 | 일치 |
| 같은 화자 3턴 연속 | 3 | 2 | 모델이 턴을 병합 |
| 3인 교대 6턴 | 6 | 1 | 전부 한 덩어리 |

END 는 우리 턴 구조가 아니라 모델 내부 판단으로 찍힙니다. 다만 병합된 경우에도
찍힌 위치는 정확했습니다(같은 화자 3턴에서 단어 수 비율 8:3 ↔ 시간 비율 5.867:2.933 일치).

**대응 (`app/timing.py`).** END 를 앵커로 쓰고 나머지를 채웁니다.

1. 단어 수 + 문장부호 정지로 각 턴의 예상 길이를 잡고 전체 길이에 맞춰 늘린다
2. END 앵커를 가장 가까운 예상 경계에 배정해 그 값으로 **고정**한다
3. 앵커가 없는 경계는 예상 위치 ±0.45초 안에서 가장 조용한 20ms 지점으로 스냅한다

실제 결과:

| 대본 | 판정 |
|---|---|
| 3인 Conversation 7턴 | 7/7 전부 모델이 준 정확한 경계 |
| Narration 3턴 (같은 화자) | 1개 정확 + 2개 무음 정렬 |

품질은 매 출력 json 의 `timing_notes` 에 문장으로 기록되므로 숨은 실패가 생기지 않습니다.

### 5-7. HF 대용량 샤드 다운로드가 끊깁니다

`microsoft/VibeVoice-1.5B` 1.97GB 샤드에서 `ChunkedEncodingError: IncompleteRead
(707213713 bytes read, 1268104115 more expected)` 발생. `snapshot_download` 는
`.incomplete` 파일을 보고 이어받으므로 **재시도 루프(최대 8회 · 8초 간격)** 를 넣어 해결했습니다.
`tools_download_models.py` / `tools_download_dia2.py` 참조.

### 5-8. VibeVoice 가 드물게 대본을 건너뜁니다 (조기 EOS)

앱 경로에서 410단어 대본이 50.1초(8.2단어/초)로 잘려 나온 사례를 실측했습니다.
정상 출력은 2.5~3.2단어/초입니다. 원인 격리 결과:

| 가설 | 결과 |
|---|---|
| 진행률 스트리머가 생성을 끊는다 | 아님 — 스트리머 유무 모두 127.7s |
| `max_length_times=2` 상한에 걸렸다 | 아님 — 4로 올려도 동일, `reach_max` 플래그도 False |
| 괄호 연기 지시가 망가뜨린다 | 아님 — 노트 포함 130.4s 정상 |
| **시드를 안 잡았다** | **원인.** `do_sample=False` 여도 확산 헤드는 매 스텝 노이즈를 뽑고, 그 음향 결과가 LLM 에 되먹임되므로 운 나쁘면 모델이 조기 EOS 를 낸다 |

**대응 (`vibevoice_engine.py`):** 기본 시드 고정(재현성) + 출력 검증
(단어수 ÷ 길이 > 4.5 단어/초면 대본을 건너뛴 것) + 시드를 바꿔 최대 2회 재시도.
Dia2 의 발산 감지(5-3)와 같은 구조입니다.

### 5-9. Windows 예약 포트에 두 번 부딪혔습니다

이 PC 는 WSL/Hyper-V 가 켜져 있어 포트 지형이 특이합니다.

- **7860 (백엔드):** `wslrelay.exe` 가 점유 중. WSL 안의 다른 FastAPI 앱이 물려 있습니다.
  기동 시 바인드 확인 후 안내를 남기고 종료 코드 3. 설정 `port` 로 변경 가능(현재 7861).
- **1420/1421 (Vite/Tauri 기본):** Hyper-V 예약 구간(1336–1435)에 걸려 `EACCES`.
  `netsh interface ipv4 show excludedportrange protocol=tcp` 로 확인했고
  예약 구간 밖인 **6420/6421** 로 옮겼습니다 (`vite.config.ts`, `tauri.conf.json`).

CORS 는 개발 포트가 또 바뀌어도 어긋나지 않게 `localhost/127.0.0.1 임의 포트 +
tauri.localhost` 정규식으로 받습니다 (서버가 127.0.0.1 전용이라 안전합니다).

### 5-10. 백엔드 기동을 0.5초로 줄였습니다

`app.main` 이 임포트 시점에 torch 를 끌어와 서버가 20~30초 동안 응답하지 못했고,
그 사이 앱이 "백엔드 없음" 화면을 띄웠습니다. torch 와 엔진 모듈 임포트를 실제 사용
시점으로 미뤄 **임포트 0.47초**가 됐습니다. `/health` 의 VRAM 은 torch 가 아직 없으면
nvidia-smi 로 읽습니다. 모델은 첫 렌더 요청에서 올라가며 그동안 UI 는
"모델을 GPU에 올리는 중" 상태를 보여줍니다.

### 5-11. Gemini 5xx 는 재시도합니다

`gemini-2.5-flash` 와 `gemini-3.7-flash` 가 실측 중 계속 503(과부하)을 냈습니다.
일시 오류(503/500/타임아웃)는 1.5→4→8초 백오프로 3회 재시도하고, 그래도 실패하면
"Gemini 서버가 지금 붐빕니다. 잠시 뒤 다시 눌러주세요." 한 문장만 보여줍니다
(원본 JSON 오류를 그대로 노출하지 않습니다). 기본 모델은 실측에서 안정적으로 응답한
최신 Flash 인 `gemini-3.6-flash` 입니다.

### 5-12. 앱 종료 시 백엔드 정리 — 두 경로 모두 검증

| 시나리오 | 결과 |
|---|---|
| 정상 종료 (창 닫기) | python 종료 · 포트 해제 · VRAM 반환 확인 |
| **강제 종료** (`TerminateProcess`, 크래시 모사) | **Job Object(`KILL_ON_JOB_CLOSE`)가 커널 수준에서 python 트리를 정리** — python 없음 · 포트 해제 · VRAM 1.4GB 복귀 확인 |

### 5-13. 포트 7860 이 이미 쓰이고 있습니다 (5-9 와 같은 문제의 최초 기록)

이 머신에서 `wslrelay.exe`(WSL) 가 7860 을 잡고 있습니다. `/voices` 로 요청하면
`{"detail":"Not Found"}` 가 오는 것으로 보아 WSL 안에서 다른 FastAPI 앱이 돌고 있습니다.
지침의 아키텍처가 7860 을 명시하고 있어 포트를 임의로 바꾸지 않았고, 대신

- 기동 시 바인드 가능 여부를 먼저 확인하고, 막혀 있으면 원인과 다음 행동을 한 줄로 로그에 남긴 뒤 종료 코드 3 으로 끝냅니다
- `--port` 인자와 설정의 `port` 로 바꿀 수 있습니다 (검증은 7861 에서 진행)

**선생님 판단이 필요합니다.** WSL 쪽 프로그램을 끄고 7860 을 쓸지, 앱 기본 포트를 옮길지.

---

## 6. 원본 코드 대비 변경 사항 (diff)

**서드파티 저장소는 한 줄도 수정하지 않았습니다.** 둘 다 고정 커밋으로 체크아웃해
`--no-deps -e` 로 설치했습니다.

앱 쪽에서 적용한 설정 변경은 하나입니다.

```diff
  C:\ai\models\VibeVoice-1.5B\preprocessor_config.json
- "language_model_pretrained_name": "Qwen/Qwen2.5-1.5B"
+ "language_model_pretrained_name": "C:\\ai\\models\\Qwen2.5-1.5B"
```

`VibeVoiceProcessor.from_pretrained` 가 이 값을 읽어 토크나이저를 찾는데, 기본값이면
매번 HuggingFace 를 조회합니다. 로컬 경로로 바꿔 **완전 오프라인 구동**이 되게 했습니다
(내부 검사가 `'qwen' in name.lower()` 라 소문자 `qwen` 이 경로에 포함되어 통과합니다).
`tools_download_models.py` 재실행 시 덮어써지므로 다운로드 스크립트의 후처리에 포함할 예정입니다.

---

## 7. 검증 결과 (1 · 2단계)

### VibeVoice-1.5B — 2인 대화 8턴

| 항목 | ddpm 10 (기본) | ddpm 5 |
|---|---|---|
| 로드 | 5.7s | 5.5s |
| VRAM 상주 | 5.04 GB | 5.04 GB |
| VRAM 피크 | 5.85 GB | 5.85 GB |
| 생성 | 86.9s | 66.0s |
| 오디오 길이 | 51.47s | 44.67s |
| **RTF** | **1.689** | 1.478 |
| attn | sdpa | sdpa |
| 클리핑 · 무음 · NaN | 0 · 0 · 없음 | 0 · 0 · 없음 |

ddpm 5 는 12% 빨라지지만 같은 대본이 44.7초로 짧아집니다(발화가 빨라짐). 이득이 작아
**기본값 10 유지.** 병목은 확산 헤드가 아니라 토큰당 LLM forward 입니다.

### Dia2-2B — 2인 대화 (CUDA 그래프 켬)

| 항목 | 값 |
|---|---|
| VRAM 상주 | 7.64 GB |
| VRAM 피크 | 8.68 GB |
| 생성 | 19.1s |
| 오디오 길이 | 25.12s |
| **RTF** | **0.761** |
| 컨텍스트 상한 | 1500 스텝 @ 12.5Hz = **정확히 120초** |

지침의 "1회 출력 2분 상한"은 Dia2 `config.json` 의 `max_context_steps: 1500` 에서
나온 값임을 확인했습니다.

### 두 엔진 동시 상주 가능 여부

5.04 + 7.64 = **12.7 GB 상주**, 피크 합산 시 약 14.5 GB.
24GB 카드에서 산술적으로는 둘 다 올라가지만, 데스크톱이 이미 2.4GB 를 쓰고 있고
피크가 겹칠 여지가 있어 **지침대로 선택된 엔진만 로드하고 전환 시 교체**합니다.

---

## 8. 재현 절차

```powershell
# 1. Python 3.11.9 (사용자 단위, C:\ai\python311)
#    python.org 설치 파일을 받아 무인 설치
python-3.11.9-amd64.exe /quiet InstallAllUsers=0 TargetDir=C:\ai\python311 `
  PrependPath=0 Include_launcher=1 InstallLauncherAllUsers=0 `
  Include_test=0 Include_doc=0 AssociateFiles=0 Shortcuts=0

# 2. venv
C:\ai\python311\python.exe -m venv C:\ai\voice-desk\backend\.venv
C:\ai\voice-desk\backend\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel

# 3. torch 를 먼저 (CPU 판으로 덮이는 것 방지)
...\python.exe -m pip install torch==2.9.1 torchaudio==2.9.1 `
  --index-url https://download.pytorch.org/whl/cu126

# 4. 나머지 의존성
...\python.exe -m pip install transformers==4.51.3 accelerate==1.6.0 diffusers `
  librosa soundfile "numpy<2.3" scipy tqdm safetensors huggingface_hub sphn

# 5. 엔진 (고정 커밋, --no-deps)
git clone https://github.com/vibevoice-community/VibeVoice.git C:\ai\voice-desk\backend\third_party\VibeVoice
git -C ...\VibeVoice checkout 952326dd
git clone https://github.com/nari-labs/dia2.git C:\ai\voice-desk\backend\third_party\dia2
...\python.exe -m pip install --no-deps -e C:\ai\voice-desk\backend\third_party\VibeVoice
...\python.exe -m pip install --no-deps -e C:\ai\voice-desk\backend\third_party\dia2

# 6. 모델
$env:HF_HOME="C:\ai\models\hf-cache"
...\python.exe backend\tools_download_models.py
...\python.exe backend\tools_download_dia2.py

# 7. 검증
...\python.exe backend\verify_vibevoice.py
...\python.exe backend\verify_dia2.py
```

---

### 5-14. 연기 지시가 그대로 발음되고, 구절 뒤에 쇠소리가 붙습니다 (사용자 청취 보고)

**① 괄호 연기 지시 발화.** 지침의 "note 는 VibeVoice 에서 텍스트 앞 괄호 지시로" 방식은
이 모델에서 동작하지 않습니다 — "(cheerful, relaxed)" 를 감정으로 해석하지 않고
그대로 읽는 것을 사용자가 확인했습니다. 대응:

- VibeVoice: note 를 프롬프트에 넣지 않음 (화면 표시 · 대본 재생성에만 사용)
- Dia2: `(laughs)` 등 알려진 비언어 태그일 때만 통과, 서술형 노트는 제외
- 미리듣기 경로도 동일, Dia2 캐시 키에 v2 를 붙여 노트가 읽힌 옛 캐시 무효화
- 검증: 13단어 + 15단어 노트 대본 → 4.7초(2.8 단어/초). 노트가 읽혔다면 10초 이상

**② 금속성 잔향("쇠소리").** 계측 결과 모든 VibeVoice 출력에서 구절 사이와 파일 꼬리에
1.8~9kHz(꼬리는 2~3kHz, 구절 사이는 4~5.6kHz) 협대역 톤이 -33~-45dBFS 로 따라붙습니다.
-16 LUFS 정규화의 +9dB 게인이 이를 들리게 만듭니다. Dia2 출력에는 없습니다.

원천 제거 시도 (실패):

| 시도 | 결과 |
|---|---|
| ddpm 스텝 10 → 20 → 30 | 금속 프레임 비율 변화 없음 |
| 보이스 교체 (Alice/Carter → Maya/Frank) | 변화 없음 |
| STFT 로 톤 피크만 도려내기 | 지표 개선 없이 발화 프레임 훼손 → 폐기 |
| flash_attention_2 (포크 권장) | 설치 금지 지침이라 시험 불가 |

채택한 완화 (기본 켬, 설정 `vv_polish` 로 끔):

- **다운워드 익스팬더** (ffmpeg compand, loudnorm 앞단): -30dBFS 이상 발화는 그대로,
  -42dBFS 는 10dB, 더 조용한 곳은 1.4:1 로 감쇠. loudnorm 1패스 측정도 같은 체인으로 재측정
- **꼬리 트림 + 80ms 페이드아웃** (마지막 발화 뒤 잔향 제거)
- 실측: 발화 평균 -16.0 dBFS 유지, 조용한 구간 -79.8 → **-124.3 dBFS**
- 청취 A/B: `Music\VoiceDesk\쇠소리AB_1_기존.mp3` vs `쇠소리AB_2_익스팬더.mp3`

## 9. 진행 현황 (2026-09-01 저녁)

- [x] `design/DIRECTION.md` 승인 (3개 항목 모두)
- [x] FastAPI 래핑 — `/health` `/voices` `/script` `/script/segment` `/render` `/tts`
      `/jobs/{id}` `/jobs/{id}/cancel` `/jobs/{id}/audio` `/audio` `/settings`
      `/gemini/models` `/cache/clear` `/engine/unload` `/shutdown`
- [x] Gemini 대본 생성 — 사용자 키로 실동작 확인, 줄 단독 재생성 포함
- [x] Tauri 스캐폴딩 · sidecar(Job Object) · 3단계 흐름 — UI 로 전 과정 실동작 확인
- [x] 히스토리(mp3 재생 복원 포함) · 설정 · 온보딩 · 단축키
- [x] NSIS 빌드 → `app\src-tauri\target\release\bundle\nsis\VoiceDesk_0.1.0_x64-setup.exe`
- [x] 설치 테스트 체크리스트 → `TESTING.md`
- [ ] Dia2 레퍼런스 클로닝 — 보류 결정(whisper-large-v3 3GB). 설정에 자리만 예정
- [ ] 포트 7860 vs 7861 — 사용자 결정 대기 (5-9 참조)
- [ ] 청취 판정 — SDPA 음질 · 5분 대화 화자 유지 · Dia2 비언어 태그

## 10. 기능 확장 (2026-09-01 저녁 2차, 전체 사용자 승인)

15개 확장 항목을 모두 구현했다. 사용자 지시 두 가지가 반영됐다:
"한국어는 성능이 검증된 것만" · "완료되면 커밋 푸시".

### 새 엔진: Supertonic 3 (한국어)

| | |
|---|---|
| 모델 | Supertone/supertonic (v3) · 99M · ONNX · MIT · 385MB |
| 실행 | **CPU** (onnxruntime) — torch/transformers 핀과 충돌 없음, VRAM 0 |
| 성능 | 한국어 8.85초를 2.53초에 합성 (RTF 0.29) |
| 보이스 | F1~F5 · M1~M5 (10종), id 접두사 `st-` |
| 관리 | GPU 엔진과 별도 슬롯 — VibeVoice/Dia2 를 내리지 않고 나란히 상주 |

**한국어 검증 (whisper-large-v3 재전사 CER):**

- 문장 10종(일상·숫자·날짜·영어혼용·긴문장·질문·감탄): 실제 발음 오류 ≈ 0%.
  표면 CER 6.6%는 전부 표기 차이("백이십팔 기가바이트"↔"128GB", "구월 일일"↔"9월 1일")
- 아라비아 숫자 입력("오후 3시 반", "45,000원", "2026년 9월 3일"): 정확히 낭독
- **유일한 실약점: 전화번호식 숫자열(010-1234-5678)** — 문서·UI 힌트로 안내
- 청취 샘플: `Music\VoiceDesk\한국어검증_Supertonic_F1.wav` / `_M2.wav` (최종 거부권은 사용자)

### 구현 항목 요약

| 항목 | 구현 |
|---|---|
| 자막 내보내기 | mp3 옆에 .srt(BOM)+.vtt, 번역 있으면 둘째 줄. 설정 `export_subtitles` |
| 재생 속도 | 트랜스포트 바 1×→0.75→0.5→1.25→1.5 순환, defaultPlaybackRate 로 src 교체에도 유지 |
| 한국어 번역 병기 | Gemini 스키마에 `translation` 추가. 표시·txt·자막·Anki 에만 쓰고 발화 안 함 |
| 보이스 미리듣기 캐시 | `GET /voices/{id}/preview` — 최초 1회 합성 후 캐시 (실측 2.5s→0.01s) |
| 포트 자동 폴백 | Rust 가 스폰 전에 빈 포트 탐색(+10), Python 도 동일 폴백 후 settings.json 기록 |
| 잔향 정리 토글 | 설정 화면에 `vv_polish` 노출 |
| 렌더 중 이어 듣기 | 엔진 → `Job.push_pcm`(int16) → `GET /jobs/{id}/pcm` → 프론트 WebAudio 스케줄링. 재시드 재시도 시 버퍼 리셋 신호 |
| Anki 내보내기 | `POST /export/anki` — ffmpeg 로 구간 컷 + genanki .apkg (오디오/문장/번역 카드) |
| 인앱 모델 다운로더 | `POST /models/download` + 온보딩 진행률. `app/downloads.py` (재시도 8회) |
| 대본 시리즈 | `ScriptRequest.previous` — 이전 화 전체를 맥락으로 "다음 화" 생성 |
| 배치 큐 | 렌더 중 요청은 자동 큐잉(GPU_LOCK 직렬화) + 우하단 QUEUE 패널 |
| Dia2 클로닝 | `references{화자:wav}` → 90초 묶음 렌더 + whisper 전사(lru 캐시 몽키패치) + 발산 재시도. 레퍼런스는 미리 24kHz 리샘플 |
| VibeVoice 부분 재렌더 | `resume_from` — 앞부분 재사용 + 30ms 크로스페이드 (실험 표시) |
| 발음 연습 | 구간 듣기(0.5×까지) → 마이크 녹음 → 비교 재생. 녹음은 저장 안 함 |
| QuickTts 확장 | 엔진 선택(VibeVoice/Supertonic) + 엔진별 보이스 필터 |

### 이 과정에서 잡은 함정

- **whisper 가 PATH 의 ffmpeg 를 부른다** → config.py 에서 동봉 bin 을 PATH 앞에 추가
- **제목에 마침표가 있으면 `with_suffix` 가 엉뚱한 곳을 자른다** → 문자열 결합으로 교체
- Supertonic 은 44.1kHz — 인코딩 시 엔진 고유 샘플레이트를 유지하도록 수정
- dia2 는 프리픽스 전사마다 whisper 를 새로 로드 → `wts.load_model` lru 캐시 래핑
- Dia2 캐시 키에 `v2` — 노트가 읽히던 시절 캐시 무효화

### 성능 실측 정리

| 항목 | 값 |
|---|---|
| VibeVoice RTF (서버 경로, verbose=False) | **0.73~0.81** — 6분 25초 대화를 280초에 렌더 |
| VibeVoice RTF (초기 CLI 측정) | 1.69 — tqdm 콘솔 출력 오버헤드가 낀 값이었다 |
| Dia2 RTF (CUDA 그래프) | 0.76 |
| 백엔드 기동 (torch 지연 임포트) | 0.47초 |
| 검증 렌더 | Narration · 3인 대화 · 6분25초 3인 · Dia2 캐시 재렌더 모두 통과 |
