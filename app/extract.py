"""Gemini → TripSpec JSON. Python validates and fills filters the model often drops."""

from __future__ import annotations

import re

from pydantic import ValidationError

from .llm import complete_json
from .trip_spec import TripSpec

EXTRACT_SYSTEM = """
Convert the user trip request into JSON for a 2026 local catalog planner.

If you can fill a complete spec, return ONLY the spec object (no "error" key).
If nights per city are missing, or the request is not a trip, return:
{"error": "incomplete", "message": "<what is missing>"}
Do not guess nights. Do not invent a return/onward flight the user did not ask for.

You MUST copy constraints the user stated. Do not leave hotel.amenities empty
or hotel.min_stars at 1 if they named stars or amenities.

Rules:
- Dates must be YYYY-MM-DD in 2026. If they omit the year, use 2026.
- legs: one object per flight hop they asked for (origin, destination, date).
  Optional per-leg time_of_day or cabin when they named it for that hop only.
- stays: one object per city they sleep in (city, nights). Optional check_in.
  Optional per-stay min_stars and amenities when that city has its own hotel ask.
- hotel / flight at the top level are defaults for stays/legs that omit overrides.
- One inbound flight per stay, plus at most one extra onward/return hop.
- cabin: economy or business (default economy).
- passengers: "2 adults" / "two people" → 2.
- hotel.min_stars: "3-star or better" / "3 star" → 3. Default 1 only if they said nothing about stars.
- hotel.amenities: required filters. Map:
  complimentary/complementary breakfast → breakfast
  gym / fitness → gym
  pool, spa, wifi, airport shuttle as stated (use airport_shuttle for shuttle).
- flight.time_of_day: afternoon / morning / night if they prefer that window.
- flight.sort_by: duration if shortest/fastest; otherwise price.
- flight.is_refundable: yes or no only if they said so.
- price_preference: cheapest (default) or most_expensive.
- budget_cap: number if they gave a budget; otherwise null.
- overage_allowed: 0 if strictly within budget; otherwise top of an allowed overage range.

Example shape (different trip from the user):
{"passengers":1,"cabin":"economy","budget_cap":2000,"overage_allowed":0,
 "price_preference":"cheapest",
 "hotel":{"min_stars":4,"amenities":["pool"]},
 "flight":{"time_of_day":"morning","min_price_usd":null,"max_price_usd":null,
           "sort_by":"price","is_refundable":null},
 "stays":[{"city":"london","nights":2,"check_in":"2026-03-01"}],
 "legs":[{"origin":"DEL","destination":"LHR","date":"2026-03-01"}]}
""".strip()

_STAR_RE = re.compile(r"(\d)\s*[- ]?\s*stars?(?:\s+or\s+better)?", re.I)

_AMENITY_PHRASES: list[tuple[str, str]] = [
    ("complimentary breakfast", "breakfast"),
    ("complementary breakfast", "breakfast"),
    ("included breakfast", "breakfast"),
    ("breakfast included", "breakfast"),
    ("breakfast", "breakfast"),
    ("fitness", "gym"),
    ("gym", "gym"),
    ("swimming pool", "pool"),
    ("pool", "pool"),
    ("airport shuttle", "airport_shuttle"),
    ("spa", "spa"),
    ("wifi", "wifi"),
    ("wi-fi", "wifi"),
]


def _enrich_from_prompt(raw: dict, prompt: str) -> dict:
    """Fill stars/amenities/time-of-day when the model omitted them but the user said them."""
    text = prompt.lower()
    hotel = dict(raw.get("hotel") or {})
    flight = dict(raw.get("flight") or {})

    stars = _STAR_RE.search(prompt)
    current_stars = hotel.get("min_stars")
    if stars and (current_stars in (None, 1, "1")):
        hotel["min_stars"] = int(stars.group(1))

    amenities = [str(a).strip().lower() for a in (hotel.get("amenities") or []) if a]
    for phrase, token in _AMENITY_PHRASES:
        if phrase in text and token not in amenities:
            amenities.append(token)
    hotel["amenities"] = amenities

    if not flight.get("time_of_day"):
        if re.search(r"\bafternoon\b", text):
            flight["time_of_day"] = "afternoon"
        elif re.search(r"\bmorning\b", text):
            flight["time_of_day"] = "morning"
        elif re.search(r"\bnight\b|\bevening\b", text):
            flight["time_of_day"] = "night"

    if re.search(r"strictly\s+(within|under|inside)", text):
        raw["overage_allowed"] = 0

    raw["hotel"] = hotel
    raw["flight"] = flight
    return raw


PATCH_SYSTEM = """
Update the trip spec JSON from a user edit. Return the FULL spec object only.
Change only what they asked (passengers, a date, a city hotel filter, a leg time_of_day).
Do not add flights or cities they did not request. Keep 2026 YYYY-MM-DD dates.
""".strip()


def patch_trip_spec(spec: TripSpec, edit: str) -> TripSpec | dict:
    """Merge a follow-up edit into an existing spec."""
    payload = f"Current spec:\n{spec.model_dump_json()}\n\nUser edit:\n{edit}"
    try:
        raw = complete_json(payload, system=PATCH_SYSTEM, schema=TripSpec.model_json_schema())
    except Exception:
        raw = complete_json(payload, system=PATCH_SYSTEM)
    if raw.get("error") and not raw.get("legs"):
        return {
            "error": str(raw.get("error") or "incomplete"),
            "message": str(raw.get("message") or "Could not apply that change."),
        }
    raw = _enrich_from_prompt(raw, edit)
    try:
        return TripSpec.model_validate(raw)
    except ValidationError as exc:
        return {
            "error": "invalid_spec",
            "message": "The updated trip spec failed validation.",
            "detail": exc.errors(),
        }


def extract_trip_spec(prompt: str) -> TripSpec | dict:
    """Return a TripSpec, or {"error", "message"} if incomplete/invalid."""
    try:
        raw = complete_json(
            prompt,
            system=EXTRACT_SYSTEM,
            schema=TripSpec.model_json_schema(),
        )
    except Exception:
        raw = complete_json(prompt, system=EXTRACT_SYSTEM)
    if raw.get("error") and not raw.get("legs"):
        return {
            "error": str(raw.get("error") or "incomplete"),
            "message": str(raw.get("message") or "Could not build a trip spec."),
        }
    raw = _enrich_from_prompt(raw, prompt)
    try:
        return TripSpec.model_validate(raw)
    except ValidationError as exc:
        return {
            "error": "invalid_spec",
            "message": "The extracted trip spec failed validation.",
            "detail": exc.errors(),
        }
