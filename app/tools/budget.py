"""Grounded totals from catalog ids. The model must not add prices itself."""

from __future__ import annotations

from .flights import get_flight
from .hotels import get_hotel


def _tokens(value) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v is not None and str(v).strip() != ""]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _ints(value, *, size: int) -> list[int]:
    if isinstance(value, (list, tuple)):
        nums = [int(v) for v in value]
    elif value is None or value == "":
        nums = []
    else:
        text = str(value).strip()
        nums = [int(part) for part in text.split(",")] if "," in text else [int(float(text))]
    if len(nums) == 1 and size > 1:
        return nums * size
    return nums


def score_budget(
    passengers: int,
    flight_offer_ids: list[str] | str | None = None,
    hotel_ids: list[str] | str | None = None,
    nights: list[int] | str | int | None = None,
    budget_cap: float | None = None,
    overage_allowed: float = 0,
    flight_offer_id: str | None = None,
    hotel_id: str | None = None,
) -> dict:
    """Look up chosen offer/hotel ids and sum a bill. Optional budget check."""
    flights = _tokens(flight_offer_ids) or _tokens(flight_offer_id)
    hotels = _tokens(hotel_ids) or _tokens(hotel_id)
    pax = int(passengers)
    if pax < 1:
        return {"ok": False, "error": "invalid_counts"}
    if not flights:
        return {"ok": False, "error": "missing_flights"}
    if not hotels:
        return {"ok": False, "error": "missing_hotels"}

    night_list = _ints(nights, size=len(hotels))
    if len(night_list) != len(hotels) or any(n < 1 for n in night_list):
        return {
            "ok": False,
            "error": "invalid_nights",
            "hotels": hotels,
            "nights": night_list,
        }

    line_items: list[dict] = []
    chosen_flights: list[dict] = []
    chosen_hotels: list[dict] = []

    for offer_id in flights:
        row = get_flight(str(offer_id))
        if not row:
            return {"ok": False, "error": "unknown_flight", "flight_offer_id": offer_id}
        amount = int(row["price_usd"]) * pax
        chosen_flights.append(row)
        line_items.append(
            {
                "type": "flight",
                "offer_id": row["offer_id"],
                "label": (
                    f"{row['flight_number']} "
                    f"{row['origin_airport']}->{row['destination_airport']}"
                ),
                "amount": amount,
            }
        )

    for hotel_key, stay_nights in zip(hotels, night_list, strict=True):
        row = get_hotel(str(hotel_key))
        if not row:
            return {"ok": False, "error": "unknown_hotel", "hotel_id": hotel_key}
        amount = int(row["cost_per_day"]) * stay_nights
        chosen_hotels.append({**row, "nights": stay_nights})
        line_items.append(
            {
                "type": "hotel",
                "hotel_id": row["hotel_id"],
                "label": f"{row['name']} x{stay_nights}n",
                "amount": amount,
            }
        )

    total = sum(item["amount"] for item in line_items)
    cap = None if budget_cap is None or budget_cap == "" else float(budget_cap)
    extra = float(overage_allowed or 0)
    ceiling = None if cap is None else cap + extra
    ok = True if ceiling is None else total <= ceiling
    return {
        "ok": ok,
        "error": None if ok else "over_budget",
        "total": total,
        "budget_cap": cap,
        "overage_allowed": extra,
        "ceiling": ceiling,
        "remaining": None if cap is None else cap - total,
        "over_by": 0 if ok or ceiling is None else round(total - ceiling, 2),
        "passengers": pax,
        "line_items": line_items,
        "flights": chosen_flights,
        "hotels": chosen_hotels,
    }
