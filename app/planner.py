"""Deterministic trip stitch: search flights + hotels, then score vs budget."""

from __future__ import annotations

from typing import Any

from .tools.flights import search_flights
from .tools.hotels import search_hotels
from .tools.timeline import evaluate_timeline
from .trip_spec import TripSpec


SHORTLIST = 5


def _flight_cost(flight: dict, passengers: int) -> int:
    return int(flight["price_usd"]) * passengers


def _hotel_cost(hotel: dict, nights: int) -> int:
    return int(hotel["cost_per_day"]) * nights


def _merge_unique(primary: list[dict], extra: list[dict], key: str, limit: int) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in [*primary, *extra]:
        token = str(row[key])
        if token in seen:
            continue
        seen.add(token)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _leg_shortlist(spec: TripSpec, leg_index: int) -> dict:
    prefs = spec.flight
    leg = spec.legs[leg_index]
    base_sort = prefs.sort_by
    if spec.price_preference == "most_expensive" and base_sort != "duration":
        base_sort = "price"
    found = search_flights(
        leg.origin,
        leg.destination,
        leg.date,
        spec.leg_cabin(leg_index),
        time_of_day=spec.leg_time_of_day(leg_index),
        min_price_usd=prefs.min_price_usd,
        max_price_usd=prefs.max_price_usd,
        sort_by=base_sort,
        is_refundable=prefs.is_refundable,
        limit=SHORTLIST,
    )
    if found.get("error") or not found.get("flights"):
        return found
    flights = list(found["flights"])
    if spec.price_preference == "most_expensive":
        high = search_flights(
            leg.origin,
            leg.destination,
            leg.date,
            spec.leg_cabin(leg_index),
            time_of_day=spec.leg_time_of_day(leg_index),
            min_price_usd=prefs.min_price_usd,
            max_price_usd=prefs.max_price_usd,
            sort_by="price_desc",
            is_refundable=prefs.is_refundable,
            limit=SHORTLIST,
        )
        flights = _merge_unique(high.get("flights") or [], flights, "offer_id", SHORTLIST * 2)
    found["flights"] = flights
    return found


def _stay_shortlist(spec: TripSpec, stay_index: int) -> dict:
    stay = spec.stays[stay_index]
    hotel = spec.stay_hotel(stay_index)
    cheap = search_hotels(
        stay.city,
        min_stars=hotel.min_stars,
        amenities=hotel.amenities,
        sort_by="price",
        limit=SHORTLIST,
    )
    if cheap.get("error") or not cheap.get("hotels"):
        return cheap
    hotels = list(cheap["hotels"])
    if spec.price_preference == "most_expensive":
        high = search_hotels(
            stay.city,
            min_stars=hotel.min_stars,
            amenities=hotel.amenities,
            sort_by="price_desc",
            limit=SHORTLIST,
        )
        hotels = _merge_unique(high.get("hotels") or [], hotels, "hotel_id", SHORTLIST * 2)
    cheap["hotels"] = hotels
    return cheap


def _timeline_ok(spec: TripSpec, flights: list[dict], hotels: list[dict]) -> bool:
    ok, _reason = evaluate_timeline(
        flights,
        hotels,
        [stay.nights for stay in spec.stays],
        [stay.city for stay in spec.stays],
        [stay.check_in for stay in spec.stays],
    )
    return ok


def _line_items(spec: TripSpec, flights: list[dict], hotels: list[dict]) -> list[dict]:
    items: list[dict] = []
    for pick in flights:
        items.append(
            {
                "type": "flight",
                "offer_id": pick["offer_id"],
                "label": (
                    f"{pick['flight_number']} "
                    f"{pick['origin_airport']}->{pick['destination_airport']}"
                ),
                "amount": _flight_cost(pick, spec.passengers),
            }
        )
    for stay, pick in zip(spec.stays, hotels, strict=True):
        items.append(
            {
                "type": "hotel",
                "hotel_id": pick["hotel_id"],
                "label": f"{pick['name']} x{stay.nights}n",
                "amount": _hotel_cost(pick, stay.nights),
            }
        )
    return items


def _pack(
    spec: TripSpec,
    flights: list[dict],
    hotels: list[dict],
    *,
    ok: bool,
    error: str | None,
) -> dict[str, Any]:
    items = _line_items(spec, flights, hotels)
    total = sum(item["amount"] for item in items)
    ceiling = spec.budget_ceiling
    remaining = None if spec.budget_cap is None else spec.budget_cap - total
    over_by = 0
    if ceiling is not None and total > ceiling:
        over_by = round(total - ceiling, 2)
    return {
        "ok": ok,
        "error": error,
        "total": total,
        "budget_cap": spec.budget_cap,
        "overage_allowed": spec.overage_allowed,
        "ceiling": ceiling,
        "remaining": remaining,
        "over_by": over_by,
        "price_preference": spec.price_preference,
        "passengers": spec.passengers,
        "line_items": items,
        "flights": flights,
        "hotels": [{**h, "nights": stay.nights} for h, stay in zip(hotels, spec.stays)],
    }


def _better(spec: TripSpec, candidate_total: int, best_total: int | None) -> bool:
    if best_total is None:
        return True
    if spec.price_preference == "most_expensive":
        return candidate_total > best_total
    return candidate_total < best_total


def plan_trip(spec: TripSpec) -> dict:
    """Search shortlists, drop illegal timelines, then pick min or max total. No LLM."""
    flight_lists: list[list[dict]] = []
    for i, leg in enumerate(spec.legs):
        found = _leg_shortlist(spec, i)
        if found.get("error") or not found.get("flights"):
            return {
                "ok": False,
                "error": "no_flights",
                "leg_index": i,
                "leg": leg.model_dump(),
                "detail": found,
            }
        flight_lists.append(found["flights"])

    hotel_lists: list[list[dict]] = []
    for i, stay in enumerate(spec.stays):
        found = _stay_shortlist(spec, i)
        if found.get("error") or not found.get("hotels"):
            return {
                "ok": False,
                "error": "no_hotels",
                "stay_index": i,
                "stay": stay.model_dump(),
                "detail": found,
            }
        hotel_lists.append(found["hotels"])

    ceiling = spec.budget_ceiling
    best_ok: tuple[list[dict], list[dict]] | None = None
    best_ok_total: int | None = None
    best_legal: tuple[list[dict], list[dict]] | None = None
    best_legal_total: int | None = None
    saw_timeline = False

    def dfs_hotels(flights: list[dict], stay_i: int, hotels: list[dict], cost: int) -> None:
        nonlocal best_ok, best_ok_total, best_legal, best_legal_total, saw_timeline
        if stay_i == len(hotel_lists):
            if not _timeline_ok(spec, flights, hotels):
                return
            saw_timeline = True
            if _better(spec, cost, best_legal_total):
                best_legal = (list(flights), list(hotels))
                best_legal_total = cost
            if ceiling is None or cost <= ceiling:
                if _better(spec, cost, best_ok_total):
                    best_ok = (list(flights), list(hotels))
                    best_ok_total = cost
            return
        nights = spec.stays[stay_i].nights
        for hotel in hotel_lists[stay_i]:
            dfs_hotels(
                flights,
                stay_i + 1,
                hotels + [hotel],
                cost + _hotel_cost(hotel, nights),
            )

    def dfs_flights(leg_i: int, flights: list[dict], cost: int) -> None:
        if leg_i == len(flight_lists):
            dfs_hotels(flights, 0, [], cost)
            return
        for flight in flight_lists[leg_i]:
            dfs_flights(
                leg_i + 1,
                flights + [flight],
                cost + _flight_cost(flight, spec.passengers),
            )

    dfs_flights(0, [], 0)

    if best_ok is not None:
        return _pack(spec, best_ok[0], best_ok[1], ok=True, error=None)
    if best_legal is not None:
        return _pack(spec, best_legal[0], best_legal[1], ok=False, error="over_budget")
    if not saw_timeline:
        return {
            "ok": False,
            "error": "timeline",
            "detail": "no flight/hotel combination satisfies check-in/checkout rules",
        }
    return {"ok": False, "error": "infeasible"}
