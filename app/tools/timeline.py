"""Check flight/hotel picks against check-in, checkout, and airport buffer."""

from __future__ import annotations

from datetime import date, timedelta

from .budget import _ints, _tokens
from .flights import get_flight
from .hotels import get_hotel, resolve_city

AIRPORT_BUFFER_HOURS = 3
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


def evaluate_timeline(
    flights: list[dict],
    hotels: list[dict],
    nights: list[int],
    stay_cities: list[str],
    check_ins: list[str | None] | None = None,
) -> tuple[bool, str | None]:
    """Inbound date = night-1 check-in; outbound is checkout morning minus buffer."""
    if len(flights) < len(hotels):
        return False, "need one inbound flight per hotel stay"
    if len(hotels) != len(nights) or len(hotels) != len(stay_cities):
        return False, "hotels, nights, and stay cities must align"
    check_ins = check_ins or [None] * len(hotels)
    for i, hotel in enumerate(hotels):
        incoming = flights[i]
        stay_nights = int(nights[i])
        stay_city = stay_cities[i]
        raw_in = check_ins[i] if i < len(check_ins) else None
        if raw_in:
            check_in = _as_date(str(raw_in))
        else:
            check_in = _as_date(incoming["arrive_date"])
        checkout = check_in + timedelta(days=stay_nights)
        if _as_date(incoming["arrive_date"]) != check_in:
            return False, f"stay {i}: inbound arrival must match check-in {check_in.isoformat()}"
        dest = incoming.get("destination_city") or incoming.get("destination_airport")
        hotel_city = hotel.get("city") or hotel.get("city_name")
        if dest and hotel_city and not _same_city(str(dest), str(hotel_city)):
            return False, f"stay {i}: inbound flight does not land in the hotel city"
        if not _same_city(stay_city, str(hotel_city or stay_city)):
            return False, f"stay {i}: hotel is not in {stay_city}"
        if i + 1 >= len(flights):
            continue
        outgoing = flights[i + 1]
        if _as_date(outgoing["depart_date"]) != checkout:
            return False, f"stay {i}: next flight must depart on checkout {checkout.isoformat()}"
        origin = outgoing.get("origin_city") or outgoing.get("origin_airport")
        if origin and hotel_city and not _same_city(str(origin), str(hotel_city)):
            return False, f"stay {i}: next flight does not leave from the hotel city"
        check_out = str(hotel.get("check_out") or DEFAULT_CHECK_OUT)
        earliest = _minutes(check_out) - AIRPORT_BUFFER_HOURS * 60
        if _minutes(outgoing["depart_time"]) < earliest:
            return False, (
                f"stay {i}: departure {outgoing['depart_time']} is too close to "
                f"checkout {check_out} (need {AIRPORT_BUFFER_HOURS}h buffer)"
            )
    return True, None


def check_timeline(
    flight_offer_ids: list[str] | str | None = None,
    hotel_ids: list[str] | str | None = None,
    nights: list[int] | str | int | None = None,
    stay_cities: list[str] | str | None = None,
    check_ins: list[str] | str | None = None,
    flight_offer_id: str | None = None,
    hotel_id: str | None = None,
) -> dict:
    """Validate chosen catalog ids against check-in/checkout/buffer rules."""
    flights_ids = _tokens(flight_offer_ids) or _tokens(flight_offer_id)
    hotels_ids = _tokens(hotel_ids) or _tokens(hotel_id)
    cities = _tokens(stay_cities)
    ins = _tokens(check_ins)
    if not flights_ids or not hotels_ids:
        return {"ok": False, "error": "missing_ids"}
    night_list = _ints(nights, size=len(hotels_ids))
    if len(night_list) != len(hotels_ids):
        return {"ok": False, "error": "invalid_nights"}
    if cities and len(cities) != len(hotels_ids):
        return {"ok": False, "error": "invalid_stay_cities"}

    flights: list[dict] = []
    for offer_id in flights_ids:
        row = get_flight(str(offer_id))
        if not row:
            return {"ok": False, "error": "unknown_flight", "flight_offer_id": offer_id}
        flights.append(row)

    hotels: list[dict] = []
    for hid in hotels_ids:
        row = get_hotel(str(hid))
        if not row:
            return {"ok": False, "error": "unknown_hotel", "hotel_id": hid}
        hotels.append(row)

    if not cities:
        cities = [str(h.get("city") or h.get("city_name") or "") for h in hotels]

    check_in_list: list[str | None] = list(ins) if ins else [None] * len(hotels)
    while len(check_in_list) < len(hotels):
        check_in_list.append(None)

    ok, reason = evaluate_timeline(flights, hotels, night_list, cities, check_in_list)
    return {
        "ok": ok,
        "error": None if ok else "timeline",
        "reason": reason,
        "flight_offer_ids": flights_ids,
        "hotel_ids": hotels_ids,
    }
