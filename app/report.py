"""Gemini writes English from a finished Python plan. It must not invent ids or money."""

from __future__ import annotations

import json
from typing import Any

from .llm import complete
from .trip_spec import TripSpec

REPORT_SYSTEM = """
You write the user-facing trip itinerary.

You are given a JSON plan already computed in Python. Use it as the only source
of flights, hotels, prices, and totals. Copy offer_id / hotel_id / amounts exactly.

- If ok is true: present the itinerary, itemized bill, total, and remaining budget
  (remaining may be null if there was no budget).
- If ok is false: explain the error clearly (over_budget, timeline, no_flights,
  no_hotels, infeasible). If line items exist, you may show them as what was
  cheapest/legal but still failed the cap. Do not invent cheaper inventory.
- Do not book or take payment. Do not add extra flights (including returns).
- Keep the tone concise.
""".strip()


def _flight_view(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "offer_id",
        "flight_number",
        "airline",
        "origin_airport",
        "destination_airport",
        "depart_date",
        "depart_time",
        "arrive_date",
        "arrive_time",
        "duration_minutes",
        "cabin",
        "price_usd",
        "is_refundable",
    )
    return {k: row[k] for k in keys if k in row}


def _hotel_view(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "hotel_id",
        "name",
        "city",
        "stars",
        "cost_per_day",
        "nights",
        "amenities",
        "check_in",
        "check_out",
        "rooms_available",
    )
    return {k: row[k] for k in keys if k in row}


def plan_payload(plan: dict[str, Any], spec: TripSpec) -> dict[str, Any]:
    return {
        "ok": plan.get("ok"),
        "error": plan.get("error"),
        "detail": plan.get("detail"),
        "total": plan.get("total"),
        "budget_cap": plan.get("budget_cap"),
        "overage_allowed": plan.get("overage_allowed"),
        "ceiling": plan.get("ceiling"),
        "remaining": plan.get("remaining"),
        "over_by": plan.get("over_by"),
        "passengers": plan.get("passengers"),
        "price_preference": plan.get("price_preference"),
        "line_items": plan.get("line_items"),
        "flights": [_flight_view(f) for f in plan.get("flights") or []],
        "hotels": [_hotel_view(h) for h in plan.get("hotels") or []],
        "spec": spec.model_dump(),
    }


def report_plan(plan: dict[str, Any], spec: TripSpec) -> str:
    body = json.dumps(plan_payload(plan, spec), default=str)
    return complete(f"Plan JSON:\n{body}", system=REPORT_SYSTEM)
