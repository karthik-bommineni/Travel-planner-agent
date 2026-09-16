"""SQLite hotel catalog lookups."""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from .db import catalog_db_path, connect
from .flights import resolve_airports

HOTEL_FIELDS = (
    "hotel_id",
    "name",
    "city",
    "city_name",
    "stars",
    "cost_per_day",
    "rooms_available",
    "amenities",
    "check_in",
    "check_out",
)


@lru_cache(maxsize=1)
def _city_keys(db_path: str) -> dict[str, str]:
    """Map hyderabad / Hyderabad / HYD → city slug used on hotel rows."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        mapping: dict[str, str] = {}
        for city, city_name, airport in conn.execute(
            "SELECT city, city_name, airport FROM airports"
        ):
            mapping[city.lower()] = city
            mapping[city_name.lower()] = city
            mapping[airport.lower()] = city
            mapping[city.replace("_", " ")] = city
        return mapping
    finally:
        conn.close()


def resolve_city(token: str, db_path: Path | None = None) -> str | None:
    path = db_path or catalog_db_path()
    raw = token.strip()
    if not raw:
        return None
    keys = _city_keys(str(path.resolve()))
    slug = raw.lower().replace(" ", "_")
    return keys.get(slug) or keys.get(raw.lower())


def _parse_amenities(blob: str) -> list[str]:
    return [p.strip().lower() for p in blob.split("|") if p.strip()]


def search_hotels(
    city: str,
    min_stars: int = 1,
    amenities: list[str] | str | None = None,
    *,
    sort_by: str | None = None,
    limit: int = 10,
    db_path: Path | None = None,
) -> dict:
    """Hotels in one city. Default cheapest room-night first. Amenities are a hard AND filter."""
    path = db_path or catalog_db_path()
    slug = resolve_city(city, path)
    if not slug:
        # IATA-only tokens still work via airports table; last resort: slug itself.
        if resolve_airports(city, path):
            slug = resolve_city(resolve_airports(city, path)[0], path)
    if not slug:
        return {"hotels": [], "error": "unknown_city", "city": city}

    stars = int(min_stars) if min_stars else 1
    stars = min(5, max(1, stars))

    if amenities is None or amenities == "":
        wanted: list[str] = []
    elif isinstance(amenities, str):
        wanted = _parse_amenities(amenities.replace(",", "|"))
    else:
        wanted = [a.strip().lower() for a in amenities if a and str(a).strip()]

    order = (sort_by or "price").strip().lower()
    if order in ("price_desc", "expensive", "most_expensive", "highest"):
        order_sql = "cost_per_day DESC, stars DESC"
        order = "price_desc"
    else:
        order_sql = "cost_per_day ASC, stars DESC"
        order = "price"

    conn = connect(path)
    try:
        rows = conn.execute(
            f"""
            SELECT {", ".join(HOTEL_FIELDS)}
            FROM hotels
            WHERE city = ?
              AND stars >= ?
              AND rooms_available >= 1
            ORDER BY {order_sql}
            """,
            (slug, stars),
        ).fetchall()
    finally:
        conn.close()

    hotels = []
    for row in rows:
        item = dict(row)
        have = set(_parse_amenities(item["amenities"]))
        if wanted and not all(a in have for a in wanted):
            continue
        item["amenities"] = sorted(have)
        hotels.append(item)
        if len(hotels) >= limit:
            break

    return {
        "city": slug,
        "min_stars": stars,
        "amenities": wanted,
        "sort_by": order,
        "hotels": hotels,
    }


def get_hotel(hotel_id: str, db_path: Path | None = None) -> dict | None:
    conn = connect(db_path)
    try:
        row = conn.execute(
            f"SELECT {', '.join(HOTEL_FIELDS)} FROM hotels WHERE hotel_id = ?",
            (hotel_id.strip(),),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    item = dict(row)
    item["amenities"] = _parse_amenities(item["amenities"])
    return item
