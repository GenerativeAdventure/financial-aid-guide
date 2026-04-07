/**
 * app.js — chat logic for US Financial Aid Guide
 */

// ---- State ----
const state = {
  history: [],       // [{role, content}]
  loading: false,
};

// ---- DOM refs ----
const chatMessages   = document.getElementById("chat-messages");
const questionInput  = document.getElementById("question-input");
const sendBtn        = document.getElementById("send-btn");
const charCount      = document.getElementById("char-count");
const modelSelect    = document.getElementById("model-select");
const btnFullGraph   = document.getElementById("btn-full-graph");
const btnFit         = document.getElementById("btn-fit");

// ---- Init ----
document.addEventListener("DOMContentLoaded", () => {
  GraphViz.init();
  GraphViz.loadFull();
  loadModels();
  bindEvents();
});

async function loadModels() {
  try {
    const res = await fetch("/api/models");
    const { models } = await res.json();
    modelSelect.innerHTML = models
      .map(m => `<option value="${m.id}">${m.label}</option>`)
      .join("");
    // Default to mini
    if (models.find(m => m.id === "gpt-4.1-mini")) {
      modelSelect.value = "gpt-4.1-mini";
    }
  } catch (e) {
    // fallback options already in HTML
  }
}

function bindEvents() {
  sendBtn.addEventListener("click", handleSend);

  questionInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  questionInput.addEventListener("input", () => {
    const len = questionInput.value.length;
    charCount.textContent = `${len} / 500`;
    charCount.style.color = len > 450 ? "#f87171" : "";
  });

  document.querySelectorAll(".example-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      questionInput.value = btn.dataset.q;
      charCount.textContent = `${btn.dataset.q.length} / 500`;
      handleSend();
    });
  });

  btnFullGraph.addEventListener("click", () => {
    GraphViz.loadFull();
    setActiveGraphBtn(btnFullGraph);
  });

  btnFit.addEventListener("click", () => {
    GraphViz.fitAll();
  });
}

function setActiveGraphBtn(btn) {
  document.querySelectorAll(".graph-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
}

// ---- Send question ----
async function handleSend() {
  const question = questionInput.value.trim();
  if (!question || state.loading) return;

  const model = modelSelect.value;

  // Clear welcome if first message
  const welcome = chatMessages.querySelector(".welcome-message");
  if (welcome) welcome.remove();

  // Render user bubble
  appendUserBubble(question);
  questionInput.value = "";
  charCount.textContent = "0 / 500";

  // Show typing indicator
  const typingEl = appendTypingIndicator();

  state.loading = true;
  sendBtn.disabled = true;

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        model,
        history: state.history,
      }),
    });

    typingEl.remove();

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Server error" }));
      appendErrorBubble(err.detail || "Something went wrong");
      return;
    }

    const data = await res.json();

    // Update history
    state.history.push({ role: "user",      content: question });
    state.history.push({ role: "assistant", content: data.answer });

    // Render answer
    appendAssistantBubble(data.answer, data.model, data.tokens_used);

    // Highlight graph nodes from subgraph
    if (data.subgraph) {
      GraphViz.showSubgraph(data.subgraph);
      setActiveGraphBtn(btnFit);
    }

  } catch (e) {
    typingEl.remove();
    appendErrorBubble("Network error — please try again.");
  } finally {
    state.loading = false;
    sendBtn.disabled = false;
    questionInput.focus();
  }
}

// ---- Render helpers ----

function appendUserBubble(text) {
  const turn = document.createElement("div");
  turn.className = "chat-turn";
  turn.innerHTML = `<div class="bubble bubble-user">${escHtml(text)}</div>`;
  chatMessages.appendChild(turn);
  scrollChat();
}

function appendAssistantBubble(text, model, tokens) {
  const turn = document.createElement("div");
  turn.className = "chat-turn";
  const modelLabel = model ? ` · ${model}` : "";
  const tokensLabel = tokens ? ` · ${tokens} tokens` : "";
  turn.innerHTML = `
    <div class="bubble bubble-assistant">${formatAnswer(text)}</div>
    <div class="bubble-meta">FSA Handbook${modelLabel}${tokensLabel}</div>
  `;
  chatMessages.appendChild(turn);
  scrollChat();
}

function appendErrorBubble(msg) {
  const turn = document.createElement("div");
  turn.className = "chat-turn";
  turn.innerHTML = `<div class="bubble bubble-assistant" style="border-color:#f87171;color:#f87171">${escHtml(msg)}</div>`;
  chatMessages.appendChild(turn);
  scrollChat();
}

function appendTypingIndicator() {
  const el = document.createElement("div");
  el.className = "chat-turn";
  el.innerHTML = `<div class="typing-indicator"><span></span><span></span><span></span></div>`;
  chatMessages.appendChild(el);
  scrollChat();
  return el;
}

function scrollChat() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Convert **bold** and line breaks to HTML (minimal markdown)
function formatAnswer(text) {
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br/>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>");
}

function escHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
