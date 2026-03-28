const WS_URL = "ws://localhost:8765";

let ws = null;
let currentMode = "voice";

function showState(id) {
  document.querySelectorAll(".state").forEach(el => el.classList.remove("active"));
  document.getElementById(id).classList.add("active");
}

function connect() {
  return new Promise((resolve, reject) => {
    ws = new WebSocket(WS_URL);
    ws.onopen = () => resolve(ws);
    ws.onerror = () => reject(new Error("Could not connect to backend"));
  });
}

function handleDoneMessage(msg) {
  if (msg.card) {
    document.getElementById("card-img").src = "data:image/png;base64," + msg.card;
    document.getElementById("card-wrap").style.display = "";
    if (currentMode === "text") {
      document.getElementById("card-wrap").classList.add("text-glow");
    } else {
      document.getElementById("card-wrap").classList.remove("text-glow");
    }
  } else {
    document.getElementById("card-wrap").style.display = "none";
  }

  if (msg.exact_words) {
    document.getElementById("exact-words").textContent = msg.exact_words;
    document.getElementById("exact-words-wrap").style.display = "";
  } else {
    document.getElementById("exact-words-wrap").style.display = "none";
  }

  showState("state-done");
  ws.close();
}

function makeMessageHandler() {
  return (event) => {
    const msg = JSON.parse(event.data);
    if (msg.status === "thinking") {
      showState("state-thinking");
    } else if (msg.status === "done") {
      handleDoneMessage(msg);
    } else if (msg.status === "error") {
      document.getElementById("error-msg").textContent = msg.message || "Something went wrong.";
      showState("state-error");
      ws.close();
    }
  };
}

function makeErrorHandler() {
  return () => {
    document.getElementById("error-msg").textContent = "Connection error.";
    showState("state-error");
  };
}

async function startSession() {
  document.getElementById("thinking-label").textContent = "Listening & thinking…";
  showState("state-thinking");
  try {
    await connect();
    ws.onmessage = makeMessageHandler();
    ws.onerror = makeErrorHandler();
    ws.send(JSON.stringify({ mode: "voice" }));
  } catch (err) {
    document.getElementById("error-msg").textContent = err.message;
    showState("state-error");
  }
}

async function startTextSession() {
  const message = document.getElementById("text-input").value.trim();
  if (!message) return;

  document.getElementById("thinking-label").textContent = "Reading & thinking…";
  showState("state-thinking");
  try {
    await connect();
    ws.onmessage = makeMessageHandler();
    ws.onerror = makeErrorHandler();
    ws.send(JSON.stringify({ mode: "text", message }));
  } catch (err) {
    document.getElementById("error-msg").textContent = err.message;
    showState("state-error");
  }
}

function setMode(mode) {
  currentMode = mode;
  document.getElementById("mode-voice-btn").classList.toggle("active", mode === "voice");
  document.getElementById("mode-text-btn").classList.toggle("active", mode === "text");
  reset();
}

function reset() {
  if (ws) {
    ws.close();
    ws = null;
  }
  showState(currentMode === "voice" ? "state-idle" : "state-text-idle");
}

document.getElementById("start-btn").addEventListener("click", startSession);
document.getElementById("cancel-btn").addEventListener("click", reset);
document.getElementById("send-btn").addEventListener("click", startTextSession);
document.getElementById("again-btn").addEventListener("click", reset);
document.getElementById("retry-btn").addEventListener("click", reset);
document.getElementById("mode-voice-btn").addEventListener("click", () => setMode("voice"));
document.getElementById("mode-text-btn").addEventListener("click", () => setMode("text"));
document.getElementById("copy-btn").addEventListener("click", () => {
  const text = document.getElementById("exact-words").textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById("copy-btn");
    btn.textContent = "Copied!";
    setTimeout(() => { btn.textContent = "Copy"; }, 2000);
  });
});
