const EXAMPLE =
  "Plan a trip for 2 adults in economy. Fly from Hyderabad (HYD) to Munich on 2026-06-15. Stay in Munich for 3 nights only — do not add a return flight or any other city. Book one 3-star or better hotel room that includes complementary breakfast and a gym. Prefer an afternoon departure if possible. Total trip budget is 4000 US dollars, strictly within budget.";

const promptEl = document.getElementById("prompt");
const sendBtn = document.getElementById("send");
const exampleBtn = document.getElementById("example");
const statusEl = document.getElementById("status");
const itineraryEl = document.getElementById("itinerary");
const bookError = document.getElementById("book-error");
const bookedToast = document.getElementById("booked-toast");
let toastTimer;

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

async function planTrip() {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    showStatus("Write a trip request first.", true);
    return;
  }
  sendBtn.disabled = true;
  itineraryEl.hidden = true;
  showStatus("Planning — this can take a little while…");
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Request failed");
    }
    itineraryEl.hidden = false;
    itineraryEl.classList.add("itinerary");
    itineraryEl.innerHTML = renderMarkdown(data.text || "");
    fillIds(data.text || "");
    showStatus("");
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

sendBtn.addEventListener("click", planTrip);

promptEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    planTrip();
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
