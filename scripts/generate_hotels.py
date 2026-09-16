"""Generate a small hotel catalog for each city in data/airports.csv."""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
from pathlib import Path

AMENITY_KITS = [
    ["wifi"],
    ["wifi", "breakfast"],
    ["wifi", "gym"],
    ["wifi", "breakfast", "gym"],
    ["wifi", "breakfast", "gym", "pool"],
    ["breakfast"],
    ["wifi", "pool"],
    ["wifi", "gym", "spa"],
    ["wifi", "breakfast", "gym", "spa", "pool"],
    ["wifi", "breakfast", "airport_shuttle"],
]

STAR_BASE_USD = {2: 70, 3: 130, 4: 220, 5: 380}

CITY_MULT = {
    "new_york": 1.45,
    "london": 1.4,
    "zurich": 1.45,
    "dubai": 1.35,
    "singapore": 1.3,
    "hong_kong": 1.3,
    "tokyo": 1.35,
    "paris": 1.3,
    "san_francisco": 1.35,
    "los_angeles": 1.2,
    "hyderabad": 0.55,
    "delhi": 0.6,
    "mumbai": 0.65,
    "bengaluru": 0.6,
    "chennai": 0.55,
    "johannesburg": 0.7,
    "manila": 0.6,
    "kuala_lumpur": 0.65,
    "bangkok": 0.7,
}

BRANDS = [
    "Central",
    "Harbour",
    "Park",
    "Grand",
    "Plaza",
    "Inn",
    "Suites",
    "Residence",
    "Palace",
    "Garden",
    "Tower",
    "Station",
]


def unique_cities(airports_csv: Path) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    with airports_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            seen[row["city"]] = row["city_name"]
    return sorted(seen.items(), key=lambda x: x[0])


def generate_rows(cities: list[tuple[str, str]], per_city: int) -> list[dict]:
    rows: list[dict] = []
    n = 0
    for city, city_name in cities:
        rng = random.Random(int(hashlib.md5(city.encode()).hexdigest()[:8], 16))
        mult = CITY_MULT.get(city, 1.0)
        for i in range(per_city):
            n += 1
            stars = [2, 3, 3, 3, 3, 4, 4, 4, 5, 5, 3, 4][i % 12]
            if i == 0:
                amenities = ["wifi"]
            elif i == 1:
                amenities = ["wifi", "breakfast"]
            elif i == 2:
                amenities = ["wifi", "gym"]
            elif i == 3:
                amenities = ["wifi", "breakfast", "gym"]
            else:
                amenities = list(AMENITY_KITS[i % len(AMENITY_KITS)])
                if "breakfast" not in amenities or "gym" not in amenities:
                    if i % 2 == 0:
                        amenities = ["wifi", "breakfast", "gym"]
            noise = rng.randint(-18, 25)
            cost = max(40, int(STAR_BASE_USD[stars] * mult) + noise)
            brand = BRANDS[i % len(BRANDS)]
            if i == 0:
                rooms_available = 0
            else:
                rooms_available = rng.randint(1, 48)
            rows.append(
                {
                    "hotel_id": f"HTL-{n:05d}",
                    "name": f"{city_name} {brand}",
                    "city": city,
                    "city_name": city_name,
                    "stars": stars,
                    "cost_per_day": cost,
                    "rooms_available": rooms_available,
                    "amenities": "|".join(amenities),
                    "check_in": "15:00",
                    "check_out": "11:00",
                }
            )
    return rows


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--airports", type=Path, default=root / "data" / "airports.csv")
    parser.add_argument("--out", type=Path, default=root / "data" / "hotels.csv")
    parser.add_argument("--per-city", type=int, default=12)
    args = parser.parse_args()
    cities = unique_cities(args.airports)
    rows = generate_rows(cities, args.per_city)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"cities={len(cities)} hotels={len(rows)} wrote {args.out}")


if __name__ == "__main__":
    main()
