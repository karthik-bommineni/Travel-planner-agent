"""Tool names, Gemini schemas, and Python dispatch. Add a tool here to extend the agent."""

from __future__ import annotations

from .budget import score_budget
from .flights import search_flights
from .hotels import search_hotels
from .timeline import check_timeline

SEARCH_FLIGHT_ARGS = {
    "origin",
    "destination",
    "date",
    "cabin_class",
    "time_of_day",
    "max_price_usd",
    "min_price_usd",
    "sort_by",
    "is_refundable",
}

SEARCH_HOTEL_ARGS = {"city", "min_stars", "amenities", "sort_by"}

CHECK_TIMELINE_ARGS = {
    "flight_offer_ids",
    "hotel_ids",
    "nights",
    "stay_cities",
    "check_ins",
    "flight_offer_id",
    "hotel_id",
}

SCORE_BUDGET_ARGS = {
    "passengers",
    "flight_offer_ids",
    "hotel_ids",
    "nights",
    "budget_cap",
    "overage_allowed",
    "flight_offer_id",
    "hotel_id",
}

DECLARATIONS = [
    {
        "name": "search_flights",
        "description": (
            "Search the local flight catalog for one origin→destination on one date "
            "(YYYY-MM-DD in 2026). Returns a shortlist of at most 5 flights. "
            "Optional: cabin_class, time_of_day, price range, "
            "sort_by (price|duration|most_expensive), is_refundable (yes|no). "
            "Does not book. Pick an offer_id only from this shortlist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"},
                "date": {"type": "string"},
                "cabin_class": {"type": "string", "enum": ["economy", "business"]},
                "time_of_day": {
                    "type": "string",
                    "enum": ["morning", "afternoon", "night"],
                },
                "min_price_usd": {"type": "number"},
                "max_price_usd": {"type": "number"},
                "sort_by": {
                    "type": "string",
                    "enum": ["price", "duration", "most_expensive"],
                },
                "is_refundable": {"type": "string", "enum": ["yes", "no"]},
            },
            "required": ["origin", "destination", "date"],
        },
    },
    {
        "name": "search_hotels",
        "description": (
            "Search hotels in one city. Returns a shortlist of at most 5 hotels. "
            "Optional min_stars, sort_by "
            "(price|most_expensive), amenities as comma-separated hard filters "
            "(e.g. gym,breakfast). Does not book. Pick a hotel_id only from this shortlist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "min_stars": {"type": "integer"},
                "amenities": {"type": "string"},
                "sort_by": {"type": "string", "enum": ["price", "most_expensive"]},
            },
            "required": ["city"],
        },
    },
    {
        "name": "score_budget",
        "description": (
            "Add up chosen flights and hotels from catalog ids. Pass offer ids from "
            "search_flights and hotel ids from search_hotels. nights is nights per "
            "hotel (one number or a matching list). Do not add money yourself. "
            "Omit budget_cap if the user did not state a budget."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "passengers": {"type": "integer"},
                "flight_offer_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "hotel_ids": {"type": "array", "items": {"type": "string"}},
                "nights": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "budget_cap": {"type": "number"},
                "overage_allowed": {"type": "number"},
                "flight_offer_id": {"type": "string"},
                "hotel_id": {"type": "string"},
            },
            "required": ["passengers"],
        },
    },
    {
        "name": "check_timeline",
        "description": (
            "Validate chosen flight and hotel ids against check-in, checkout, and "
            "a 3-hour airport buffer. Pass the same ids as score_budget, nights per "
            "stay, and stay_cities. Call this after score_budget. If ok is false, "
            "pick different ids from the shortlists and score again."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "flight_offer_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "hotel_ids": {"type": "array", "items": {"type": "string"}},
                "nights": {"type": "array", "items": {"type": "integer"}},
                "stay_cities": {"type": "array", "items": {"type": "string"}},
                "check_ins": {"type": "array", "items": {"type": "string"}},
                "flight_offer_id": {"type": "string"},
                "hotel_id": {"type": "string"},
            },
            "required": ["flight_offer_ids", "hotel_ids", "nights"],
        },
    },
]

SHORTLIST = 5


def _search_flights(**kwargs):
    kwargs.pop("limit", None)
    return search_flights(**kwargs, limit=SHORTLIST)


def _search_hotels(**kwargs):
    kwargs.pop("limit", None)
    return search_hotels(**kwargs, limit=SHORTLIST)


DISPATCH = {
    "search_flights": (_search_flights, SEARCH_FLIGHT_ARGS),
    "search_hotels": (_search_hotels, SEARCH_HOTEL_ARGS),
    "score_budget": (score_budget, SCORE_BUDGET_ARGS),
    "check_timeline": (check_timeline, CHECK_TIMELINE_ARGS),
}


def run_tool(name: str, args: dict) -> dict:
    if name not in DISPATCH:
        return {"ok": False, "error": "unknown_tool", "name": name}
    fn, allowed = DISPATCH[name]
    cleaned = {k: v for k, v in dict(args).items() if k in allowed}
    result = fn(**cleaned)
    if isinstance(result, dict):
        from ..metrics import observe_tool  # late import; avoid cycles if any

        ok = result.get("ok")
        if ok is None:
            ok = not result.get("error")
        observe_tool(name, bool(ok))
    return result
