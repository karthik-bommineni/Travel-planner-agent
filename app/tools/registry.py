"""Tool names, Gemini schemas, and Python dispatch. Add a tool here to extend the agent."""

from __future__ import annotations

from .budget import score_budget
from .flights import search_flights
from .hotels import search_hotels

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
            "(YYYY-MM-DD in 2026). Optional: cabin_class, time_of_day, price range, "
            "sort_by (price|duration|most_expensive), is_refundable (yes|no). "
            "Does not book. Use most_expensive when the user wants the priciest flights."
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
            "Search hotels in one city. Optional min_stars, sort_by "
            "(price|most_expensive), amenities as comma-separated hard filters "
            "(e.g. gym,breakfast). Does not book."
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
]

DISPATCH = {
    "search_flights": (search_flights, SEARCH_FLIGHT_ARGS),
    "search_hotels": (search_hotels, SEARCH_HOTEL_ARGS),
    "score_budget": (score_budget, SCORE_BUDGET_ARGS),
}


def run_tool(name: str, args: dict) -> dict:
    if name not in DISPATCH:
        return {"ok": False, "error": "unknown_tool", "name": name}
    fn, allowed = DISPATCH[name]
    cleaned = {k: v for k, v in dict(args).items() if k in allowed}
    return fn(**cleaned)
