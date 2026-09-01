# VoiceDesk

주제를 넣으면 대본을 쓰고, 검토한 뒤 다화자 음성으로 만들어 mp3 로 저장하는 개인용 Windows 앱.

```
주제 · 형식 입력  ──▶  대본 검토 · 수정  ──▶  렌더 · 저장
   Gemini              구간 단위 편집          VibeVoice / Dia2
```

상용 배포용이 아닙니다. RTX 4090 이 달린 이 PC 한 대에서 돌아가는 것을 전제로 만들었습니다.

---

## 무엇을 만드는가

한 번 렌더하면 같은 폴더에 파일이 나란히 떨어집니다.

```
20260901_커피 원두 고르는 법_Conversation.mp3    128kbps · -16 LUFS
20260901_커피 원두 고르는 법_Conversation.txt    화자별 대본 (+한국어 번역)
20260901_커피 원두 고르는 법_Conversation.json   구간별 시작 · 끝 초
20260901_커피 원두 고르는 법_Conversation.srt    자막 (원문 + 번역)
20260901_커피 원두 고르는 법_Conversation.apkg   Anki 덱 (버튼으로 생성)
```

학습 도구가 함께 들어 있습니다: **렌더 중 이어 듣기**(합성된 부분부터 재생),
**재생 속도 0.5~1.5×**(음정 유지), 구간 반복, **발음 연습**(듣고 → 따라 말하고 →
비교), **다음 화**(같은 인물로 이어지는 에피소드), Dia2 **내 목소리 클로닝**.

`json` 은 어느 문장이 몇 초에 나오는지를 담고 있습니다. 앱 안에서는 이 값이
세그먼트 레일과 파형 마커로 보이고, 밖에서는 자막이나 학습 자료로 쓸 수 있습니다.

```json
{
  "engine": "vibevoice",
  "duration": 40.667,
  "timings_estimated": false,
  "timing_notes": ["세그먼트 경계를 모델 출력에서 그대로 읽었습니다."],
  "segments": [
    { "index": 0, "speaker": "A", "start": 0.0, "end": 8.4, "text": "Okay, I need help..." }
  ]
}
```

`timing_notes` 는 경계를 얼마나 정확히 알아냈는지 문장으로 적어둡니다.
자세한 배경은 `SETUP.md` 5-6 절에 있습니다.

---

## 엔진 세 개

| | VibeVoice 1.5B | Dia2 2B | Supertonic 3 |
|---|---|---|---|
| 역할 | 기본 (영·중) | 보조 (영) | 한국어·다국어 |
| 화자 | 최대 4명 | 2명 | 제한 없음 (구간별 스타일) |
| RTF | **0.73~0.81** | **0.76** (CUDA 그래프) | **0.29 (CPU!)** |
| VRAM 상주 | 5.0 GB | 7.6 GB | 0 (onnxruntime CPU) |
| 생성 방식 | 결정론적 | 샘플링 | 결정론적 |
| 강점 | 긴 대화 목소리 유지 | 줄 재합성 · **내 목소리 클로닝** | 한국어 · 초고속 · 가벼움 |

**GPU 엔진은 하나만 상주**하고 바꿀 때 교체합니다. Supertonic 은 CPU 라
GPU 엔진과 나란히 떠 있어도 아무것도 차지하지 않습니다.

한국어는 whisper-large-v3 재전사 검증을 거쳤습니다 — 실제 발음 오류 ≈ 0%,
숫자·날짜·금액 낭독 정확(예외: 전화번호식 숫자열은 부정확).

Dia2 는 줄 단위로 합성하고 내용 해시로 캐시합니다. 그래서 대본에서 한 줄만 고치면
**그 줄만** 다시 만듭니다. 실측으로 4줄짜리 대본에서 25.2초 → 3.3초였습니다.

6분 25초짜리 3인 대화(1,208단어)를 280초에 렌더했습니다 — 두 엔진 모두
실시간보다 빠릅니다.

---

## 쓰는 법

```powershell
# 백엔드만 따로 띄우기 (앱을 쓰면 자동으로 뜹니다)
cd C:\ai\voice-desk\backend
.\.venv\Scripts\python.exe -m app.main

# 앱 개발 모드
cd C:\ai\voice-desk\app
npm run tauri dev

# 설치본 만들기
npm run tauri build
```

첫 실행이면 온보딩이 뜹니다. Gemini 키를 넣고, GPU 와 모델이 보이는지 확인하고,
샘플을 한 번 만들어보면 끝입니다.

### 단축키

| 키 | 동작 |
|---|---|
| `Ctrl + Enter` | 대본 만들기 / 음성 만들기 (지금 단계에 따라) |
| `Space` | 재생 · 정지 |
| `Ctrl + S` | 저장한 폴더 열기 |
| `Esc` | 설정 닫기 |

---

## 구조

```
C:\ai\
├─ python311\              3.11.9 (한글 경로를 피해 여기 둠)
├─ models\                 가중치 · HF 캐시
└─ voice-desk\
   ├─ backend\             FastAPI · 127.0.0.1 에서만 수신
   │  ├─ app\
   │  │  ├─ main.py        엔드포인트
   │  │  ├─ engines\       vibevoice_engine · dia2_engine · manager
   │  │  ├─ timing.py      세그먼트 경계 산출
   │  │  ├─ script_gen.py  Gemini
   │  │  ├─ audio.py       ffmpeg · 라우드니스 · 품질 점검
   │  │  ├─ jobs.py        백그라운드 작업 · 진행률
   │  │  └─ secrets_store.py  Windows 자격 증명 관리자
   │  ├─ bin\              동봉 ffmpeg
   │  └─ third_party\      VibeVoice · dia2 (고정 커밋)
   ├─ app\                 Tauri 2 + React 18 + Tailwind
   └─ design\DIRECTION.md  디자인 방향
```

### 엔드포인트

| | |
|---|---|
| `GET /health` | GPU · VRAM · 모델 설치 여부 · 키 등록 여부 |
| `GET /voices` | 보이스 프리셋 목록 |
| `POST /script` | 주제 · 형식 → 대본 JSON |
| `POST /script/segment` | 한 줄만 다시 쓰기 |
| `POST /render` | 대본 → mp3 (백그라운드 작업) |
| `POST /tts` | 단문 한 화자 |
| `GET /jobs/{id}` | 진행률 · 결과 |
| `POST /jobs/{id}/cancel` | 취소 |
| `GET/PUT /settings` | 설정 |
| `POST /shutdown` | sidecar 종료 |

---

## 비밀값

Gemini 키와 HF 토큰은 **Windows 자격 증명 관리자**에만 들어갑니다
(`keyring` → `WinVaultKeyring`). 설정 파일 · 로그 · 히스토리 어디에도 값이 남지
않고, 예외 메시지에 섞여 나가는 것도 `secrets_store.redact()` 로 한 번 더 막습니다.

앱에서 키를 지우려면 설정에서 빈 값으로 저장하면 됩니다. 자격 증명 관리자에서
직접 지우려면 `voice-desk` 항목을 찾으세요.

---

## 백엔드가 앱과 함께 죽는 것

파이썬이 GPU 메모리를 5~8 GB 쥐고 있으므로 앱만 닫히고 백엔드가 남으면 곤란합니다.
정상 종료 경로(`CloseRequested` → `/shutdown`) 외에 **Windows Job Object** 를
하나 더 겁니다. 자식 프로세스를 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 가 걸린
Job 에 넣어두면 앱이 크래시하거나 강제 종료돼도 커널이 파이썬을 정리합니다.

---

## 디자인

`design/DIRECTION.md` 에 무드 · 토큰 · 모션 · 상태 설계가 다 있습니다. 요약하면

- **조용한 스튜디오 장비.** 무채색 섀시, 실크스크린 라벨, 램프 세 개
- **앰버(`#E2A356`)는 신호가 있을 때만 켜진다.** 버튼 · 로고 · 탭에는 절대 안 쓴다
- **세그먼트 레일**이 시그니처. 대본 왼쪽 세로 레일이 곧 타임라인이고,
  ②단계와 ③단계를 같은 물건의 두 상태로 잇는다
- 로딩 스피너 대신 경과 시간과 남은 시간을 숫자로 보여준다. 8분 기다리는 사람에게
  스피너는 정보가 아니다

---

## 알아둘 것

- **영어 · 중국어만 제대로 됩니다.** VibeVoice 의 공식 지원 언어가 그렇습니다.
  한국어는 미검증 교차언어 전이라 품질이 불안정합니다.
- **flash-attn 을 쓰지 않습니다.** SDPA 로 고정했습니다. 원 저장소는 SDPA 에서
  음질이 떨어질 수 있다고 경고하지만, 계측상 이상은 없었습니다.
- **Dia2 출력이 가끔 발산합니다.** 샘플링이라 시드 운이 나쁘면 왜곡된 소리가 납니다.
  피크 · 클리핑 · RMS 를 검사해 자동으로 시드를 바꿔 다시 만듭니다.
- 자세한 제약과 우회는 `SETUP.md` 5절에 있습니다.
