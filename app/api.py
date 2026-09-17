"""HTTP API for the trip planner. CLI remains python -m app.main."""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .metrics import observe_plan, observe_request, render_metrics
from .planner import plan_trip
from .session import run_turn
from .tools.flights import get_flight
from .tools.hotels import get_hotel
from .trip_spec import TripSpec

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"

app = FastAPI(title="Travel planner", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    text: str
    steps: list[dict] = Field(default_factory=list)
    session_id: str
    status: str


class BookFlightRequest(BaseModel):
    offer_id: str
    passengers: int = Field(default=1, ge=1, le=9)


class BookHotelRequest(BaseModel):
    hotel_id: str
    nights: int = Field(ge=1, le=30)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    observe_request(
        request.url.path,
        request.method,
        response.status_code,
        time.perf_counter() - start,
    )
    return response


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


@app.get("/metrics")
def metrics():
    body, media = render_metrics()
    return Response(content=body, media_type=media)


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    turn = run_turn(body.prompt, body.session_id, trace=False)
    observe_plan(turn.status)
    return ChatResponse(
        text=turn.text,
        steps=turn.steps,
        session_id=turn.session_id,
        status=turn.status,
    )


@app.post("/chat/stream")
def chat_stream(body: ChatRequest):
    events: queue.Queue = queue.Queue()

    def emit(event: dict) -> None:
        events.put(event)

    def work() -> None:
        try:
            turn = run_turn(
                body.prompt,
                body.session_id,
                trace=False,
                on_event=emit,
            )
            observe_plan(turn.status)
        except Exception as exc:  # noqa: BLE001
            events.put({"type": "error", "message": str(exc)})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def sse():
        while True:
            item = events.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")


@app.post("/plan")
def plan(spec: TripSpec):
    return plan_trip(spec)


@app.post("/book_flights")
def book_flights(body: BookFlightRequest):
    row = get_flight(body.offer_id)
    if not row:
        raise HTTPException(status_code=404, detail="unknown offer_id")
    return {
        "ok": True,
        "booking_ref": f"FL-{uuid.uuid4().hex[:8].upper()}",
        "offer_id": row["offer_id"],
        "flight_number": row["flight_number"],
        "passengers": body.passengers,
        "amount": int(row["price_usd"]) * body.passengers,
        "status": "confirmed_dummy",
    }


@app.post("/book_hotels")
def book_hotels(body: BookHotelRequest):
    row = get_hotel(body.hotel_id)
    if not row:
        raise HTTPException(status_code=404, detail="unknown hotel_id")
    if int(row.get("rooms_available") or 0) < 1:
        raise HTTPException(status_code=409, detail="no rooms available")
    return {
        "ok": True,
        "booking_ref": f"HT-{uuid.uuid4().hex[:8].upper()}",
        "hotel_id": row["hotel_id"],
        "nights": body.nights,
        "amount": int(row["cost_per_day"]) * body.nights,
        "status": "confirmed_dummy",
    }


@app.get("/")
def home():
    return FileResponse(FRONTEND / "index.html")


app.mount("/assets", StaticFiles(directory=str(FRONTEND)), name="assets")
