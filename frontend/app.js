const EXAMPLE =
  "Plan a trip for 2 adults in economy. Fly from Hyderabad (HYD) to Munich on 2026-06-15. Stay in Munich for 3 nights only — do not add a return flight or any other city. Book one 3-star or better hotel room that includes complementary breakfast and a gym. Prefer an afternoon departure if possible. Total trip budget is 4000 US dollars, strictly within budget.";

const promptEl = document.getElementById("prompt");
const sendBtn = document.getElementById("send");
const exampleBtn = document.getElementById("example");
const resetBtn = document.getElementById("reset");
const statusEl = document.getElementById("status");
const itineraryEl = document.getElementById("itinerary");
const traceEl = document.getElementById("trace");
const bookError = document.getElementById("book-error");
const bookedToast = document.getElementById("booked-toast");
let toastTimer;
let sessionId = null;
let liveText = "";

function showStatus(text, isError = false) {
  statusEl.hidden = !text;
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderMarkdown(text) {
  const escaped = escapeHtml(text);
  const withBold = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const lines = withBold.split("\n");
  const html = [];
  let list = [];

  const flushList = () => {
    if (!list.length) return;
    html.push(`<ul>${list.map((item) => `<li>${item}</li>`).join("")}</ul>`);
    list = [];
  };

  for (const line of lines) {
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      list.push(bullet[1]);
      continue;
    }
    flushList();
    if (line.trim() === "") continue;
    html.push(`<p>${line}</p>`);
  }
  flushList();
  return html.join("");
}

function fillIds(text) {
  const flight = text.match(/FLT-\d+/);
  const hotel = text.match(/HTL-\d+/);
  if (flight) {
    document.querySelector('#book-flight [name="offer_id"]').value = flight[0];
  }
  if (hotel) {
    document.querySelector('#book-hotel [name="hotel_id"]').value = hotel[0];
  }
}

function addTraceChip(step) {
  traceEl.hidden = false;
  const ids = (step.shortlist || []).slice(0, 5).join(", ");
  const extra = step.total != null ? ` · $${step.total}` : ids ? ` · ${ids}` : "";
  const err = step.error ? ` · ${step.error}` : "";
  const li = document.createElement("li");
  li.textContent = `${step.name || "tool"}${extra}${err}`;
  traceEl.appendChild(li);
}

function showItinerary(text) {
  itineraryEl.hidden = false;
  itineraryEl.classList.add("itinerary");
  itineraryEl.innerHTML = renderMarkdown(text);
  fillIds(text);
}

function handleEvent(event) {
  if (event.type === "status") {
    showStatus(event.message || "Working…");
    return;
  }
  if (event.type === "tool") {
    showStatus(`Calling ${event.name}…`);
    return;
  }
  if (event.type === "tool_result") {
    addTraceChip(event);
    return;
  }
  if (event.type === "text") {
    if (event.append) {
      liveText = `${liveText}\n\n${event.text || ""}`;
    } else {
      liveText = event.text || "";
    }
    showItinerary(liveText);
    showStatus("");
    return;
  }
  if (event.type === "error") {
    showStatus(event.message || "Something went wrong.", true);
    return;
  }
  if (event.type === "done" && event.session_id) {
    sessionId = event.session_id;
  }
}

async function readSse(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk
        .split("\n")
        .filter((row) => row.startsWith("data:"))
        .map((row) => row.slice(5).trim())
        .join("");
      if (!line) continue;
      handleEvent(JSON.parse(line));
    }
  }
}

async function sendMessage() {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    showStatus("Write a trip request first.", true);
    return;
  }
  sendBtn.disabled = true;
  if (!sessionId) {
    traceEl.innerHTML = "";
    traceEl.hidden = true;
    liveText = "";
  }
  showStatus("Planning…");
  try {
    const response = await fetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, session_id: sessionId }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Request failed");
    }
    await readSse(response);
    promptEl.value = "";
    promptEl.placeholder = "confirm — or change people, dates, a flight, a hotel…";
  } catch (err) {
    showStatus(err.message || "Could not plan this trip.", true);
  } finally {
    sendBtn.disabled = false;
  }
}

function flashBooked() {
  clearTimeout(toastTimer);
  bookedToast.hidden = false;
  const label = bookedToast.querySelector("span");
  label.style.animation = "none";
  void label.offsetWidth;
  label.style.animation = "";
  toastTimer = setTimeout(() => {
    bookedToast.hidden = true;
  }, 1350);
}

function showBookError(text) {
  bookError.hidden = !text;
  bookError.textContent = text || "";
}

async function postBook(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : JSON.stringify(data);
    throw new Error(message || "Booking failed");
  }
  return data;
}

exampleBtn.addEventListener("click", () => {
  promptEl.value = EXAMPLE;
  promptEl.focus();
});

resetBtn.addEventListener("click", () => {
  sessionId = null;
  liveText = "";
  traceEl.innerHTML = "";
  traceEl.hidden = true;
  itineraryEl.hidden = true;
  itineraryEl.innerHTML = "";
  promptEl.placeholder =
    "2 adults, economy, Hyderabad to Munich on 2026-06-15, 3 nights, 3-star with breakfast and gym, afternoon flight, budget $4000, no return…";
  showStatus("Started a new trip.");
});

sendBtn.addEventListener("click", sendMessage);

promptEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    sendMessage();
  }
});

document.getElementById("book-flight").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  showBookError("");
  try {
    await postBook("/book_flights", {
      offer_id: String(form.get("offer_id") || "").trim(),
      passengers: Number(form.get("passengers") || 1),
    });
    flashBooked();
  } catch (err) {
    showBookError(err.message);
  }
});

document.getElementById("book-hotel").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  showBookError("");
  try {
    await postBook("/book_hotels", {
      hotel_id: String(form.get("hotel_id") || "").trim(),
      nights: Number(form.get("nights") || 1),
    });
    flashBooked();
  } catch (err) {
    showBookError(err.message);
  }
});
