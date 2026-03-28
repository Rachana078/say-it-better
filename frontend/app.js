const WS_URL = "ws://localhost:8765";

let ws = null;
let currentMode = "voice";

const MODE_COLORS = {
  voice:  { color: "#f59e0b", rgb: "245, 158, 11" },
  text:   { color: "#3b82f6", rgb: "59, 130, 246" },
  decide: { color: "#8b5cf6", rgb: "139, 92, 246" },
};

const SUBTITLES = {
  voice:  "Talk it out. Get the words.",
  text:   "Type it. We say it for you.",
  decide: "Talk it out. We'll tell you what you already decided.",
};

const IDLE_STATES = {
  voice:  "state-idle",
  text:   "state-text-idle",
  decide: "state-decide-idle",
};

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

function applyModeColor(mode) {
  const { color, rgb } = MODE_COLORS[mode];
  document.documentElement.style.setProperty("--mode-color", color);
  document.documentElement.style.setProperty("--mode-rgb", rgb);
}

function handleDoneMessage(msg) {
  if (msg.exact_words) {
    document.getElementById("exact-words").textContent = msg.exact_words;
    document.getElementById("exact-label").textContent =
      currentMode === "text" ? "What was said:" : "Say exactly:";
    document.getElementById("exact-words-wrap").style.display = "";
  } else {
    document.getElementById("exact-words-wrap").style.display = "none";
  }

  showState("state-done");
  ws.close();
}

function handleDecideDoneMessage(msg) {
  document.getElementById("decide-verdict").textContent = msg.verdict || "";

  if (msg.card_a) {
    document.getElementById("card-a-img").src = "data:image/png;base64," + msg.card_a;
    document.getElementById("card-a-img").style.display = "";
  } else {
    document.getElementById("card-a-img").style.display = "none";
  }

  if (msg.card_b) {
    document.getElementById("card-b-img").src = "data:image/png;base64," + msg.card_b;
    document.getElementById("card-b-img").style.display = "";
  } else {
    document.getElementById("card-b-img").style.display = "none";
  }

  showState("state-decide-reveal");
  ws.close();
}

function makeMessageHandler() {
  return (event) => {
    const msg = JSON.parse(event.data);
    if (msg.status === "thinking") {
      showState("state-thinking");
    } else if (msg.status === "done") {
      if (msg.mode === "decide") {
        handleDecideDoneMessage(msg);
      } else {
        handleDoneMessage(msg);
      }
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

function setThinking(label) {
  document.getElementById("thinking-label").textContent = label;
}

async function startSession() {
  setThinking("Listening & thinking…");
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

  setThinking("Reading & thinking…");
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

async function startDecideSession() {
  setThinking("Reading between the lines…");
  showState("state-thinking");
  try {
    await connect();
    ws.onmessage = makeMessageHandler();
    ws.onerror = makeErrorHandler();
    ws.send(JSON.stringify({ mode: "decide" }));
  } catch (err) {
    document.getElementById("error-msg").textContent = err.message;
    showState("state-error");
  }
}

function setMode(mode) {
  currentMode = mode;
  applyModeColor(mode);
  document.getElementById("mode-voice-btn").classList.toggle("active", mode === "voice");
  document.getElementById("mode-text-btn").classList.toggle("active", mode === "text");
  document.getElementById("mode-decide-btn").classList.toggle("active", mode === "decide");
  document.getElementById("subtitle").textContent = SUBTITLES[mode];
  reset();
}

function reset() {
  if (ws) {
    ws.close();
    ws = null;
  }
  showState(IDLE_STATES[currentMode] || "state-idle");
}

document.getElementById("start-btn").addEventListener("click", startSession);
document.getElementById("send-btn").addEventListener("click", startTextSession);
document.getElementById("decide-btn").addEventListener("click", startDecideSession);
document.getElementById("cancel-btn").addEventListener("click", reset);
document.getElementById("again-btn").addEventListener("click", reset);
document.getElementById("decide-again-btn").addEventListener("click", reset);
document.getElementById("retry-btn").addEventListener("click", reset);
document.getElementById("mode-voice-btn").addEventListener("click", () => setMode("voice"));
document.getElementById("mode-text-btn").addEventListener("click", () => setMode("text"));
document.getElementById("mode-decide-btn").addEventListener("click", () => setMode("decide"));
document.getElementById("copy-btn").addEventListener("click", () => {
  const text = document.getElementById("exact-words").textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById("copy-btn");
    btn.textContent = "Copied!";
    setTimeout(() => { btn.textContent = "Copy"; }, 2000);
  });
});
