"""Deterministic trip stitch: search flights + hotels, then score vs budget."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .tools.flights import search_flights
from .tools.hotels import resolve_city, search_hotels
from .trip_spec import TripSpec

AIRPORT_BUFFER_HOURS = 3
SHORTLIST = 5
DEFAULT_CHECK_OUT = "11:00"


def _minutes(hhmm: str) -> int:
    raw = str(hhmm).strip()[:5]
    hours, mins = raw.split(":")
    return int(hours) * 60 + int(mins)


def _as_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _same_city(a: str, b: str) -> bool:
    left = resolve_city(a)
    right = resolve_city(b)
    if left and right:
        return left == right
    return a.strip().lower() == b.strip().lower()


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


def _leg_shortlist(spec: TripSpec, origin: str, destination: str, day: str) -> dict:
    prefs = spec.flight
    base_sort = prefs.sort_by
    if spec.price_preference == "most_expensive" and base_sort != "duration":
        base_sort = "price"
    found = search_flights(
        origin,
        destination,
        day,
        spec.cabin,
        time_of_day=prefs.time_of_day,
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
            origin,
            destination,
            day,
            spec.cabin,
            time_of_day=prefs.time_of_day,
            min_price_usd=prefs.min_price_usd,
            max_price_usd=prefs.max_price_usd,
            sort_by="price_desc",
            is_refundable=prefs.is_refundable,
            limit=SHORTLIST,
        )
        flights = _merge_unique(high.get("flights") or [], flights, "offer_id", SHORTLIST * 2)
    found["flights"] = flights
    return found


def _stay_shortlist(spec: TripSpec, city: str) -> dict:
    cheap = search_hotels(
        city,
        min_stars=spec.hotel.min_stars,
        amenities=spec.hotel.amenities,
        sort_by="price",
        limit=SHORTLIST,
    )
    if cheap.get("error") or not cheap.get("hotels"):
        return cheap
    hotels = list(cheap["hotels"])
    if spec.price_preference == "most_expensive":
        high = search_hotels(
            city,
            min_stars=spec.hotel.min_stars,
            amenities=spec.hotel.amenities,
            sort_by="price_desc",
            limit=SHORTLIST,
        )
        hotels = _merge_unique(high.get("hotels") or [], hotels, "hotel_id", SHORTLIST * 2)
    cheap["hotels"] = hotels
    return cheap


def _stay_check_in(spec: TripSpec, stay_index: int, incoming: dict) -> date:
    stay = spec.stays[stay_index]
    if stay.check_in:
        return _as_date(stay.check_in)
    return _as_date(incoming["arrive_date"])


def _timeline_ok(spec: TripSpec, flights: list[dict], hotels: list[dict]) -> bool:
    """Inbound date = night-1 check-in; outbound is checkout morning minus buffer."""
    for i, stay in enumerate(spec.stays):
        incoming = flights[i]
        hotel = hotels[i]
        check_in = _stay_check_in(spec, i, incoming)
        checkout = check_in + timedelta(days=stay.nights)
        if _as_date(incoming["arrive_date"]) != check_in:
            return False
        dest = incoming.get("destination_city") or incoming.get("destination_airport")
        hotel_city = hotel.get("city") or hotel.get("city_name")
        if dest and hotel_city and not _same_city(str(dest), str(hotel_city)):
            return False
        if not _same_city(stay.city, str(hotel_city or stay.city)):
            return False
        if i + 1 >= len(flights):
            continue
        outgoing = flights[i + 1]
        if _as_date(outgoing["depart_date"]) != checkout:
            return False
        origin = outgoing.get("origin_city") or outgoing.get("origin_airport")
        if origin and hotel_city and not _same_city(str(origin), str(hotel_city)):
            return False
        check_out = str(hotel.get("check_out") or DEFAULT_CHECK_OUT)
        earliest = _minutes(check_out) - AIRPORT_BUFFER_HOURS * 60
        if _minutes(outgoing["depart_time"]) < earliest:
            return False
    return True


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
        found = _leg_shortlist(spec, leg.origin, leg.destination, leg.date)
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
        found = _stay_shortlist(spec, stay.city)
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
