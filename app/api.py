"""HTTP API for the trip planner. CLI remains main.py."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .pipeline import run_pipeline
from .planner import plan_trip
from .tools.flights import get_flight
from .tools.hotels import get_hotel
from .trip_spec import TripSpec

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"

app = FastAPI(title="Travel planner", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)


class ChatResponse(BaseModel):
    text: str


class BookFlightRequest(BaseModel):
    offer_id: str
    passengers: int = Field(default=1, ge=1, le=9)


class BookHotelRequest(BaseModel):
    hotel_id: str
    nights: int = Field(ge=1, le=30)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    text = run_pipeline(body.prompt, trace=False)
    return ChatResponse(text=text)


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
