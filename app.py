import os
import re
import tempfile
from typing import Dict, List, Literal
from uuid import uuid4

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_upstage import UpstageDocumentParseLoader
from pydantic import BaseModel, Field
from pypdf import PdfReader


load_dotenv()

app = FastAPI(title="AI Interview Agent")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SESSIONS: Dict[str, dict] = {}


class HRAnalysis(BaseModel):
    applicant_name: str = Field(description="이력서에서 추출한 지원자 이름")
    keywords: List[str] = Field(description="면접에 활용할 핵심 기술/경험 키워드 3~5개")


class InterviewerAction(BaseModel):
    question: str = Field(description="지원자에게 던질 다음 질문")
    is_finished: bool = Field(description="평가로 넘어가도 되면 True")


class EvaluatorResult(BaseModel):
    status: Literal["PASS", "FAIL"] = Field(description="최종 판정")
    reasoning: str = Field(description="최종 판정 사유 3문장 이내")
    strengths: List[str] = Field(description="지원자의 강점 2~4개")
    concerns: List[str] = Field(description="보완점 또는 우려 사항 2~4개")


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


FALLBACK_KEYWORDS = ["Python", "LangChain", "LLM", "API 연동", "프로젝트 경험"]
FALLBACK_QUESTIONS = [
    "이력서에서 가장 자신 있는 프로젝트 하나를 선택해, 문제 상황과 본인이 맡은 역할을 구체적으로 설명해주세요.",
    "해당 프로젝트에서 기술적으로 가장 어려웠던 부분은 무엇이었고, 어떤 기준으로 해결 방법을 선택했나요?",
    "LLM 또는 API 연동 과정에서 응답 품질, 비용, 속도 중 어떤 요소를 가장 중요하게 관리했는지 사례로 설명해주세요.",
    "협업 중 요구사항이 바뀌었을 때 구조를 어떻게 조정했는지 말해주세요.",
    "다시 구현한다면 개선하고 싶은 부분과 그 이유는 무엇인가요?",
]


def get_llm() -> ChatAnthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY가 필요합니다.")

    return ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        temperature=0.2,
        api_key=api_key,
    )


def should_use_demo_fallback() -> bool:
    return os.getenv("DEMO_FALLBACK", "true").lower() in {"1", "true", "yes", "on"}


def parse_resume(uploaded_file: UploadFile) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.file.read())
        tmp_path = tmp.name

    try:
        local_text = extract_pdf_text_locally(tmp_path)
        if len(local_text.strip()) >= 200:
            return local_text

        upstage_key = os.getenv("UPSTAGE_API_KEY")
        if not upstage_key:
            raise HTTPException(
                status_code=500,
                detail="PDF 텍스트 추출에 실패했고 UPSTAGE_API_KEY도 설정되지 않았습니다.",
            )

        loader = UpstageDocumentParseLoader(
            tmp_path,
            api_key=upstage_key,
            split="element",
            output_format="markdown",
        )
        return "\n".join(doc.page_content for doc in loader.load())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"이력서 PDF 분석 중 오류가 발생했습니다: {exc}",
        ) from exc
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def extract_pdf_text_locally(file_path: str) -> str:
    reader = PdfReader(file_path)
    page_texts = []
    for page in reader.pages:
        page_texts.append(page.extract_text() or "")
    return "\n".join(page_texts)


def analyze_resume(llm: ChatAnthropic, resume_text: str) -> HRAnalysis:
    prompt = f"""다음 이력서를 분석하여 지원자 이름과 면접용 핵심 키워드를 추출하세요.

[이력서]
{resume_text}
"""
    return llm.with_structured_output(HRAnalysis).invoke([HumanMessage(content=prompt)])


def fallback_analysis(resume_text: str) -> HRAnalysis:
    name = "지원자"
    name_match = re.search(r"이름\s*[:：]\s*([가-힣A-Za-z]{2,20})", resume_text)
    if name_match:
        name = name_match.group(1)
        return HRAnalysis(applicant_name=name, keywords=FALLBACK_KEYWORDS)

    for line in resume_text.splitlines():
        clean = line.strip()
        if (
            clean
            and len(clean) <= 20
            and not any(char.isdigit() for char in clean)
            and "[" not in clean
            and "]" not in clean
            and ":" not in clean
        ):
            name = clean
            break
    return HRAnalysis(applicant_name=name, keywords=FALLBACK_KEYWORDS)


def history_messages(session: dict) -> list:
    messages = []
    for item in session["messages"]:
        if item["role"] == "assistant":
            messages.append(AIMessage(content=item["content"]))
        else:
            messages.append(HumanMessage(content=item["content"]))
    return messages


def generate_question(llm: ChatAnthropic, session: dict) -> InterviewerAction:
    count = session["question_count"]
    system = SystemMessage(
        content=f"""
당신은 친절하지만 검증력이 강한 기술 면접관입니다.
지원자: {session['applicant_name']}
핵심 키워드: {session['keywords']}

[이력서 요약 자료]
{session['resume_text'][:6000]}

[진행 규칙]
- 현재까지 질문 횟수는 {count}회입니다.
- 질문이 3회 미만이면 반드시 다음 질문을 하세요.
- 3회 이상이면 답변이 충분한지 판단하여 종료할 수 있습니다.
- 질문은 하나만 작성하고, 지원자가 구체적인 경험과 판단 근거를 말하게 만드세요.
"""
    )
    messages = history_messages(session)
    if not messages:
        messages = [HumanMessage(content="면접을 시작하고 첫 번째 질문을 해주세요.")]

    action = llm.with_structured_output(InterviewerAction).invoke([system] + messages)
    if action.is_finished and count < 3:
        action.is_finished = False
    return action


def fallback_question(session: dict) -> InterviewerAction:
    count = session["question_count"]
    if count >= 3:
        return InterviewerAction(question="", is_finished=True)
    return InterviewerAction(
        question=FALLBACK_QUESTIONS[min(count, len(FALLBACK_QUESTIONS) - 1)],
        is_finished=False,
    )


def evaluate_interview(llm: ChatAnthropic, session: dict) -> EvaluatorResult:
    prompt = HumanMessage(
        content=f"""
당신은 냉철한 채용 평가자입니다.
이력서와 면접 대화 기록을 바탕으로 지원자의 역량을 PASS 또는 FAIL로 평가하세요.
사유는 실제 답변 내용에 근거해 간결하게 작성하세요.

[지원자]
{session['applicant_name']}

[핵심 키워드]
{session['keywords']}

[이력서]
{session['resume_text'][:8000]}
"""
    )
    return llm.with_structured_output(EvaluatorResult).invoke(
        history_messages(session) + [prompt]
    )


def fallback_evaluation(session: dict) -> EvaluatorResult:
    answer_count = sum(1 for message in session["messages"] if message["role"] == "user")
    status = "PASS" if answer_count >= 3 else "FAIL"
    return EvaluatorResult(
        status=status,
        reasoning="API 연결 실패로 데모 평가가 생성되었습니다. 답변의 구체성, 문제 해결 과정, 기술 키워드 설명 여부를 기준으로 임시 판정했습니다.",
        strengths=["프로젝트 경험을 기반으로 답변을 구성함", "기술 키워드와 역할을 연결해 설명하려는 흐름이 있음"],
        concerns=["실제 LLM 평가가 아니므로 최종 판단에는 API 연결 후 재평가가 필요함", "정량적 성과와 트러블슈팅 근거를 더 보강할 필요가 있음"],
    )


def send_slack_notification(session: dict) -> None:
    token = os.getenv("SLACK_BOT_TOKEN")
    channel_id = os.getenv("SLACK_CHANNEL_ID")
    if not token or not channel_id or not session.get("evaluation"):
        return

    evaluation = session["evaluation"]
    keywords = ", ".join(session["keywords"])
    text = (
        f"*AI 면접 평가 완료*\n"
        f"- 지원자: {session['applicant_name']}\n"
        f"- 판정: *{evaluation['status']}*\n"
        f"- 핵심 키워드: {keywords}\n"
        f"- 사유: {evaluation['reasoning']}"
    )

    try:
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"channel": channel_id, "text": text},
            timeout=10,
        )
        result = response.json()
        if not result.get("ok"):
            print(f"[Slack 알림 실패] {result}")
    except Exception as exc:
        print(f"[Slack 알림 실패] {exc}")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/start")
def start_interview(resume: UploadFile = File(...)) -> dict:
    if resume.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    llm = get_llm()
    resume_text = parse_resume(resume)
    try:
        analysis = analyze_resume(llm, resume_text)
    except Exception as exc:
        if not should_use_demo_fallback():
            raise HTTPException(
                status_code=502,
                detail=f"이력서 핵심 정보 추출 중 오류가 발생했습니다: {exc}",
            ) from exc
        analysis = fallback_analysis(resume_text)
    session_id = str(uuid4())
    session = {
        "session_id": session_id,
        "resume_text": resume_text,
        "applicant_name": analysis.applicant_name,
        "keywords": analysis.keywords,
        "messages": [],
        "question_count": 0,
        "is_finished": False,
        "evaluation": None,
    }

    try:
        action = generate_question(llm, session)
    except Exception as exc:
        if not should_use_demo_fallback():
            raise HTTPException(
                status_code=502,
                detail=f"첫 면접 질문 생성 중 오류가 발생했습니다: {exc}",
            ) from exc
        action = fallback_question(session)
    session["messages"].append({"role": "assistant", "content": action.question})
    session["question_count"] += 1
    SESSIONS[session_id] = session
    return public_session(session)


@app.post("/api/answer")
def answer_interview(payload: AnswerRequest) -> dict:
    session = SESSIONS.get(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="면접 세션을 찾을 수 없습니다.")
    if session["is_finished"]:
        return public_session(session)

    session["messages"].append({"role": "user", "content": payload.answer})
    llm = get_llm()
    try:
        action = generate_question(llm, session)
    except Exception as exc:
        if not should_use_demo_fallback():
            raise HTTPException(
                status_code=502,
                detail=f"면접 질문 생성 중 오류가 발생했습니다: {exc}",
            ) from exc
        action = fallback_question(session)

    if action.is_finished or session["question_count"] >= 5:
        session["is_finished"] = True
        try:
            session["evaluation"] = evaluate_interview(llm, session).model_dump()
        except Exception as exc:
            if not should_use_demo_fallback():
                raise HTTPException(
                    status_code=502,
                    detail=f"최종 평가 생성 중 오류가 발생했습니다: {exc}",
                ) from exc
            session["evaluation"] = fallback_evaluation(session).model_dump()
        send_slack_notification(session)
    else:
        session["messages"].append({"role": "assistant", "content": action.question})
        session["question_count"] += 1

    return public_session(session)


def public_session(session: dict) -> dict:
    return {
        "session_id": session["session_id"],
        "applicant_name": session["applicant_name"],
        "keywords": session["keywords"],
        "messages": session["messages"],
        "question_count": session["question_count"],
        "is_finished": session["is_finished"],
        "evaluation": session["evaluation"],
    }
