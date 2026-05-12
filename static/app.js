let sessionId = null;

const statusEl = document.getElementById("status");
const errorBox = document.getElementById("errorBox");
const messagesEl = document.getElementById("messages");
const startBtn = document.getElementById("startBtn");
const sendBtn = document.getElementById("sendBtn");
const answerEl = document.getElementById("answer");
const resumeEl = document.getElementById("resume");
const fileNameEl = document.getElementById("fileName");

function setBusy(isBusy, label = "Ready") {
  statusEl.textContent = label;
  startBtn.disabled = isBusy;
  sendBtn.disabled = isBusy || !sessionId;
  answerEl.disabled = isBusy || !sessionId;
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.style.display = "block";
}

function clearError() {
  errorBox.style.display = "none";
  errorBox.textContent = "";
}

function render(data) {
  sessionId = data.session_id;
  document.getElementById("name").textContent = data.applicant_name;
  document.getElementById("questionCount").textContent = data.question_count;
  document.getElementById("questionCountTop").textContent = data.question_count;

  const keywords = document.getElementById("keywords");
  keywords.innerHTML = "";
  data.keywords.forEach((item) => {
    const chip = document.createElement("div");
    chip.className = "chip";
    chip.textContent = item;
    keywords.appendChild(chip);
  });

  messagesEl.innerHTML = "";
  data.messages.forEach((message) => {
    const row = document.createElement("div");
    row.className = `message-row ${message.role}-row`;

    const avatar = document.createElement("div");
    avatar.className = `avatar ${message.role}-avatar`;
    avatar.textContent = message.role === "assistant" ? "AI" : "ME";

    const content = document.createElement("div");
    content.className = "message-content";

    const speaker = document.createElement("div");
    speaker.className = "speaker";
    speaker.textContent = message.role === "assistant" ? "면접관" : "지원자";

    const bubble = document.createElement("div");
    bubble.className = `bubble ${message.role}`;
    bubble.textContent = message.content;

    content.appendChild(speaker);
    content.appendChild(bubble);
    row.appendChild(avatar);
    row.appendChild(content);
    messagesEl.appendChild(row);
  });
  messagesEl.scrollTop = messagesEl.scrollHeight;

  const result = document.getElementById("result");
  result.innerHTML = "";
  if (data.evaluation) {
    const cls = data.evaluation.status === "PASS" ? "pass" : "fail";
    result.innerHTML = `
      <h2>최종 평가</h2>
      <div class="result-card">
        <div class="result-status ${cls}">${data.evaluation.status}</div>
        <p>${data.evaluation.reasoning}</p>
        <div class="label">강점</div>
        <ul>${data.evaluation.strengths.map((x) => `<li>${x}</li>`).join("")}</ul>
        <div class="label">보완점</div>
        <ul>${data.evaluation.concerns.map((x) => `<li>${x}</li>`).join("")}</ul>
      </div>
    `;
  }

  if (data.is_finished) {
    answerEl.disabled = true;
    sendBtn.disabled = true;
    statusEl.textContent = "Finished";
  }
}

async function parseResponse(response) {
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "요청 처리 중 오류가 발생했습니다.");
  }
  return data;
}

resumeEl.addEventListener("change", () => {
  const file = resumeEl.files[0];
  fileNameEl.textContent = file ? file.name : "선택된 파일 없음";
});

startBtn.addEventListener("click", async () => {
  clearError();
  const file = resumeEl.files[0];
  if (!file) {
    showError("이력서 PDF를 먼저 선택해주세요.");
    return;
  }

  const formData = new FormData();
  formData.append("resume", file);

  try {
    sessionId = null;
    setBusy(true, "Analyzing resume...");
    const response = await fetch("/api/start", { method: "POST", body: formData });
    render(await parseResponse(response));
    setBusy(false, "Interviewing");
  } catch (error) {
    showError(error.message);
    setBusy(false);
  }
});

sendBtn.addEventListener("click", async () => {
  const answer = answerEl.value.trim();
  if (!answer) return;

  try {
    setBusy(true, "Thinking...");
    answerEl.value = "";
    const response = await fetch("/api/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, answer }),
    });
    const data = await parseResponse(response);
    render(data);
    if (!data.is_finished) setBusy(false, "Interviewing");
  } catch (error) {
    showError(error.message);
    setBusy(false, "Interviewing");
  }
});

answerEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    sendBtn.click();
  }
});
