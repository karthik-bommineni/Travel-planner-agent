"""SQLite flight catalog lookups."""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from .db import catalog_db_path, connect

FLIGHT_FIELDS = (
    "offer_id",
    "flight_number",
    "airline",
    "origin_city",
    "origin_airport",
    "destination_city",
    "destination_airport",
    "depart_date",
    "depart_time",
    "arrive_date",
    "arrive_time",
    "duration_minutes",
    "stops",
    "cabin",
    "price_usd",
    "seats_available",
    "is_refundable",
)


def get_flight(offer_id: str, db_path: Path | None = None) -> dict | None:
    conn = connect(db_path)
    try:
        row = conn.execute(
            f"SELECT {', '.join(FLIGHT_FIELDS)} FROM flights WHERE offer_id = ?",
            (offer_id.strip(),),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


@lru_cache(maxsize=1)
def _airport_maps(db_path: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        by_code: dict[str, str] = {}
        by_name: dict[str, list[str]] = {}
        for city, city_name, airport in conn.execute(
            "SELECT city, city_name, airport FROM airports"
        ):
            by_code[airport.upper()] = airport
            for key in {city.lower(), city_name.lower(), airport.lower()}:
                by_name.setdefault(key, [])
                if airport not in by_name[key]:
                    by_name[key].append(airport)
        return by_code, by_name
    finally:
        conn.close()


# depart_time is HH:MM local at origin. Night wraps across midnight.
TIME_OF_DAY_SQL = {
    "morning": "depart_time >= '05:00' AND depart_time < '12:00'",
    "afternoon": "depart_time >= '12:00' AND depart_time < '17:00'",
    "night": "(depart_time >= '17:00' OR depart_time < '05:00')",
}


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _optional_int(value) -> int | None:
    if _blank(value):
        return None
    return int(float(value))


def _time_of_day(value: str | None) -> str | None:
    if _blank(value):
        return None
    key = str(value).strip().lower()
    aliases = {
        "morning": "morning",
        "am": "morning",
        "afternoon": "afternoon",
        "pm": "afternoon",
        "evening": "night",
        "night": "night",
        "overnight": "night",
    }
    return aliases.get(key)


def _sort_by(value: str | None) -> str:
    if _blank(value):
        return "price"
    key = str(value).strip().lower()
    if key in ("duration", "fastest", "shortest", "least_travel_time", "time"):
        return "duration"
    if key in (
        "price_desc",
        "price_high",
        "expensive",
        "most_expensive",
        "highest",
        "luxury",
    ):
        return "price_desc"
    return "price"


def _refundable(value) -> str | None:
    """Map tool input to catalog values yes/no. None = do not filter."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    key = str(value).strip().lower()
    if key in ("any", "either"):
        return None
    if key in ("yes", "true", "1", "refundable", "y"):
        return "yes"
    if key in ("no", "false", "0", "nonrefundable", "non-refundable", "n"):
        return "no"
    return None


def resolve_airports(token: str, db_path: Path | None = None) -> list[str]:
    """Map 'HYD', 'hyd', 'Hyderabad', 'New York' → one or more IATA codes."""
    path = db_path or catalog_db_path()
    raw = token.strip()
    if not raw:
        return []
    by_code, by_name = _airport_maps(str(path.resolve()))
    upper = raw.upper()
    if upper in by_code:
        return [by_code[upper]]
    slug = raw.lower().replace(" ", "_")
    return list(by_name.get(slug) or by_name.get(raw.lower()) or [])


def search_flights(
    origin: str,
    destination: str,
    date: str,
    cabin_class: str = "economy",
    time_of_day: str | None = None,
    max_price_usd: int | float | str | None = None,
    min_price_usd: int | float | str | None = None,
    sort_by: str | None = None,
    is_refundable: str | bool | None = None,
    *,
    limit: int = 10,
    db_path: Path | None = None,
) -> dict:
    """Return up to `limit` flights for one OD/date/cabin.

    Optional filters (omit when the user did not specify them):
    - time_of_day: morning (05:00–11:59), afternoon (12:00–16:59), night (17:00–04:59)
    - min_price_usd / max_price_usd: inclusive price range
    - sort_by: price (default) or duration (least travel time via duration_minutes)
    - is_refundable: yes or no (omit to include both)
    """
    path = db_path or catalog_db_path()
    origin_aps = resolve_airports(origin, path)
    dest_aps = resolve_airports(destination, path)
    if not origin_aps or not dest_aps:
        return {
            "flights": [],
            "error": "unknown_airport",
            "origin": origin,
            "destination": destination,
        }

    cabin = (cabin_class or "economy").strip().lower()
    if cabin not in ("economy", "business"):
        cabin = "economy"

    depart_date = date.strip()
    if not (len(depart_date) == 10 and depart_date[4] == "-" and depart_date[7] == "-"):
        return {
            "flights": [],
            "error": "date_must_be_yyyy_mm_dd",
            "date": date,
        }

    tod = _time_of_day(time_of_day)
    if time_of_day and not _blank(time_of_day) and tod is None:
        return {
            "flights": [],
            "error": "invalid_time_of_day",
            "time_of_day": time_of_day,
        }

    try:
        min_price = _optional_int(min_price_usd)
        max_price = _optional_int(max_price_usd)
    except (TypeError, ValueError):
        return {
            "flights": [],
            "error": "invalid_price",
            "min_price_usd": min_price_usd,
            "max_price_usd": max_price_usd,
        }

    order = _sort_by(sort_by)
    refund_provided = isinstance(is_refundable, bool) or not _blank(is_refundable)
    refund = _refundable(is_refundable) if refund_provided else None
    if refund_provided and refund is None:
        key = str(is_refundable).strip().lower()
        if key not in ("any", "either"):
            return {
                "flights": [],
                "error": "invalid_is_refundable",
                "is_refundable": is_refundable,
            }

    if order == "duration":
        order_sql = "duration_minutes ASC, price_usd ASC, depart_time ASC"
    elif order == "price_desc":
        order_sql = "price_usd DESC, depart_time ASC"
    else:
        order_sql = "price_usd ASC, depart_time ASC"

    o_ph = ",".join("?" for _ in origin_aps)
    d_ph = ",".join("?" for _ in dest_aps)
    where = [
        f"origin_airport IN ({o_ph})",
        f"destination_airport IN ({d_ph})",
        "depart_date = ?",
        "cabin = ?",
    ]
    params: list = [*origin_aps, *dest_aps, depart_date, cabin]
    if tod:
        where.append(TIME_OF_DAY_SQL[tod])
    if min_price is not None:
        where.append("price_usd >= ?")
        params.append(min_price)
    if max_price is not None:
        where.append("price_usd <= ?")
        params.append(max_price)
    if refund is not None:
        where.append("is_refundable = ?")
        params.append(refund)
    params.append(limit)

    conn = connect(path)
    try:
        rows = conn.execute(
            f"""
            SELECT {", ".join(FLIGHT_FIELDS)}
            FROM flights
            WHERE {" AND ".join(where)}
            ORDER BY {order_sql}
            LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    return {
        "origin_airports": origin_aps,
        "destination_airports": dest_aps,
        "depart_date": depart_date,
        "cabin": cabin,
        "time_of_day": tod,
        "min_price_usd": min_price,
        "max_price_usd": max_price,
        "sort_by": order,
        "is_refundable": refund,
        "flights": [dict(r) for r in rows],
    }
