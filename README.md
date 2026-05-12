# AI Interview Agent

이력서 PDF를 분석해 지원자 핵심 키워드를 추출하고, LLM 기반 기술 면접 질문과 최종 평가를 제공하는 FastAPI 웹앱입니다. 면접 종료 시 Slack 채널로 평가 결과 알림을 보냅니다.

## 주요 기능

- PDF 이력서 업로드 및 텍스트 추출
- 지원자 이름과 핵심 기술 키워드 자동 추출
- 이력서 기반 기술 면접 질문 생성
- 답변 흐름에 따른 후속 질문 진행
- PASS/FAIL, 판단 사유, 강점, 보완점 구조화
- Slack 평가 완료 알림
- API 오류 시 데모 질문/평가 fallback 지원

## 기술 스택

- Backend: Python, FastAPI
- LLM: Anthropic Claude, LangChain
- Document AI: Upstage Document Parse, pypdf
- UI: HTML, CSS, JavaScript
- Integration: Slack API

## Screenshots

### Interview Start

![Interview Start](screenshots/web-interview-start.png)

### Final Evaluation

![Final Evaluation](screenshots/web-final-evaluation.png)

### Slack Notification

![Slack Notification](screenshots/slack-notification.png)

## 폴더 구조

```text
interview_agent_project/
├─ app.py                           # FastAPI API 및 AI 면접 로직
├─ templates/
│  └─ index.html                    # 웹 화면 구조
├─ static/
│  ├─ styles.css                    # 웹 화면 스타일
│  └─ app.js                        # 파일 업로드/면접 진행 로직
├─ screenshots/                     # README용 실행 화면
├─ data/
│  └─ .gitkeep                      # 로컬 PDF 보관용, 실제 PDF는 Git 제외
├─ .env.example
├─ .gitignore
├─ requirements.txt
└─ README.md
```

## 실행 준비

```bash
pip install -r requirements.txt
```

`.env.example`을 참고해 `.env`를 만듭니다.

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
UPSTAGE_API_KEY=your_upstage_api_key
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_CHANNEL_ID=CXXXXXXXX
DEMO_FALLBACK=true
```

`DEMO_FALLBACK=true`이면 LLM/API 호출이 실패했을 때 데모 질문과 임시 평가로 화면 흐름을 계속 확인할 수 있습니다. 실제 API 실패를 바로 확인하고 싶다면 `false`로 변경합니다.

## 실행

```bash
uvicorn app:app --reload
```

브라우저에서 접속합니다.

```text
http://127.0.0.1:8000
```

## Slack 알림 설정

FastAPI 웹앱은 면접 최종 평가가 생성될 때 Slack `chat.postMessage` API로 알림을 보냅니다.

1. Slack API에서 앱을 만들고 Bot Token Scopes에 `chat:write`를 추가합니다.
2. 앱을 워크스페이스에 설치한 뒤 `xoxb-...` 형식의 Bot User OAuth Token을 `.env`의 `SLACK_BOT_TOKEN`에 넣습니다.
3. 알림을 받을 채널에서 `/invite @앱이름`으로 앱을 초대합니다.
4. 채널 상세 정보 하단에서 `C...`로 시작하는 채널 ID를 확인해 `.env`의 `SLACK_CHANNEL_ID`에 넣습니다.

## 이력서 한 줄 소개 예시

AI 면접 에이전트: 이력서 PDF를 파싱해 지원자 핵심 역량을 추출하고, LLM 기반 기술 면접 질문 생성 및 최종 합불 평가와 Slack 알림을 제공하는 FastAPI 웹 서비스 구현
