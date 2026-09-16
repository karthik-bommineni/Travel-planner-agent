"""Generate the v1 flight catalog for calendar year 2026.

Math (default):
  50 airports, all directed pairs: 50 * 49 = 2,450 routes
  10 distinct flights per route per day (so a search like HYD→MUC
  on one date still has 10 options after filtering by cabin)
  2 cabins (economy, business)
  365 days in 2026

  2,450 * 10 * 2 * 365 = 17,885,000 rows

The plain CSV would be ~2GB, so the default output is gzip-compressed
CSV (pandas/read_csv opens .gz). Pass --plain to write an uncompressed file.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from pathlib import Path

YEAR = 2026
DATE_START = date(YEAR, 1, 1)
DATE_END = date(YEAR, 12, 31)
FLIGHTS_PER_ROUTE_PER_DAY = 10
CABINS = ("economy", "business")

# Top ~50 well-known/busy airports. utc_offset is standard time (no DST) for v1.
AIRPORTS: list[dict] = [
    {"city": "atlanta", "city_name": "Atlanta", "airport": "ATL", "lat": 33.6407, "lon": -84.4277, "utc_offset": -5.0},
    {"city": "dallas", "city_name": "Dallas", "airport": "DFW", "lat": 32.8998, "lon": -97.0403, "utc_offset": -6.0},
    {"city": "denver", "city_name": "Denver", "airport": "DEN", "lat": 39.8561, "lon": -104.6737, "utc_offset": -7.0},
    {"city": "chicago", "city_name": "Chicago", "airport": "ORD", "lat": 41.9742, "lon": -87.9073, "utc_offset": -6.0},
    {"city": "los_angeles", "city_name": "Los Angeles", "airport": "LAX", "lat": 33.9416, "lon": -118.4085, "utc_offset": -8.0},
    {"city": "new_york", "city_name": "New York", "airport": "JFK", "lat": 40.6413, "lon": -73.7781, "utc_offset": -5.0},
    {"city": "new_york", "city_name": "New York", "airport": "EWR", "lat": 40.6895, "lon": -74.1745, "utc_offset": -5.0},
    {"city": "san_francisco", "city_name": "San Francisco", "airport": "SFO", "lat": 37.6213, "lon": -122.3790, "utc_offset": -8.0},
    {"city": "las_vegas", "city_name": "Las Vegas", "airport": "LAS", "lat": 36.0840, "lon": -115.1537, "utc_offset": -8.0},
    {"city": "miami", "city_name": "Miami", "airport": "MIA", "lat": 25.7959, "lon": -80.2870, "utc_offset": -5.0},
    {"city": "seattle", "city_name": "Seattle", "airport": "SEA", "lat": 47.4502, "lon": -122.3088, "utc_offset": -8.0},
    {"city": "boston", "city_name": "Boston", "airport": "BOS", "lat": 42.3656, "lon": -71.0096, "utc_offset": -5.0},
    {"city": "london", "city_name": "London", "airport": "LHR", "lat": 51.4700, "lon": -0.4543, "utc_offset": 0.0},
    {"city": "paris", "city_name": "Paris", "airport": "CDG", "lat": 49.0097, "lon": 2.5479, "utc_offset": 1.0},
    {"city": "amsterdam", "city_name": "Amsterdam", "airport": "AMS", "lat": 52.3105, "lon": 4.7683, "utc_offset": 1.0},
    {"city": "frankfurt", "city_name": "Frankfurt", "airport": "FRA", "lat": 50.0379, "lon": 8.5622, "utc_offset": 1.0},
    {"city": "munich", "city_name": "Munich", "airport": "MUC", "lat": 48.3538, "lon": 11.7861, "utc_offset": 1.0},
    {"city": "madrid", "city_name": "Madrid", "airport": "MAD", "lat": 40.4983, "lon": -3.5676, "utc_offset": 1.0},
    {"city": "rome", "city_name": "Rome", "airport": "FCO", "lat": 41.8003, "lon": 12.2389, "utc_offset": 1.0},
    {"city": "barcelona", "city_name": "Barcelona", "airport": "BCN", "lat": 41.2974, "lon": 2.0833, "utc_offset": 1.0},
    {"city": "zurich", "city_name": "Zurich", "airport": "ZRH", "lat": 47.4582, "lon": 8.5555, "utc_offset": 1.0},
    {"city": "vienna", "city_name": "Vienna", "airport": "VIE", "lat": 48.1103, "lon": 16.5697, "utc_offset": 1.0},
    {"city": "berlin", "city_name": "Berlin", "airport": "BER", "lat": 52.3667, "lon": 13.5033, "utc_offset": 1.0},
    {"city": "copenhagen", "city_name": "Copenhagen", "airport": "CPH", "lat": 55.6180, "lon": 12.6508, "utc_offset": 1.0},
    {"city": "lisbon", "city_name": "Lisbon", "airport": "LIS", "lat": 38.7742, "lon": -9.1342, "utc_offset": 0.0},
    {"city": "istanbul", "city_name": "Istanbul", "airport": "IST", "lat": 41.2753, "lon": 28.7519, "utc_offset": 3.0},
    {"city": "dubai", "city_name": "Dubai", "airport": "DXB", "lat": 25.2532, "lon": 55.3657, "utc_offset": 4.0},
    {"city": "doha", "city_name": "Doha", "airport": "DOH", "lat": 25.2731, "lon": 51.6080, "utc_offset": 3.0},
    {"city": "abu_dhabi", "city_name": "Abu Dhabi", "airport": "AUH", "lat": 24.4330, "lon": 54.6511, "utc_offset": 4.0},
    {"city": "delhi", "city_name": "Delhi", "airport": "DEL", "lat": 28.5562, "lon": 77.1000, "utc_offset": 5.5},
    {"city": "mumbai", "city_name": "Mumbai", "airport": "BOM", "lat": 19.0896, "lon": 72.8656, "utc_offset": 5.5},
    {"city": "hyderabad", "city_name": "Hyderabad", "airport": "HYD", "lat": 17.2313, "lon": 78.4299, "utc_offset": 5.5},
    {"city": "bengaluru", "city_name": "Bengaluru", "airport": "BLR", "lat": 13.1986, "lon": 77.7066, "utc_offset": 5.5},
    {"city": "chennai", "city_name": "Chennai", "airport": "MAA", "lat": 12.9941, "lon": 80.1709, "utc_offset": 5.5},
    {"city": "singapore", "city_name": "Singapore", "airport": "SIN", "lat": 1.3644, "lon": 103.9915, "utc_offset": 8.0},
    {"city": "hong_kong", "city_name": "Hong Kong", "airport": "HKG", "lat": 22.3080, "lon": 113.9185, "utc_offset": 8.0},
    {"city": "seoul", "city_name": "Seoul", "airport": "ICN", "lat": 37.4602, "lon": 126.4407, "utc_offset": 9.0},
    {"city": "tokyo", "city_name": "Tokyo", "airport": "HND", "lat": 35.5494, "lon": 139.7798, "utc_offset": 9.0},
    {"city": "tokyo", "city_name": "Tokyo", "airport": "NRT", "lat": 35.7720, "lon": 140.3929, "utc_offset": 9.0},
    {"city": "beijing", "city_name": "Beijing", "airport": "PEK", "lat": 40.0799, "lon": 116.6031, "utc_offset": 8.0},
    {"city": "shanghai", "city_name": "Shanghai", "airport": "PVG", "lat": 31.1443, "lon": 121.8083, "utc_offset": 8.0},
    {"city": "bangkok", "city_name": "Bangkok", "airport": "BKK", "lat": 13.6900, "lon": 100.7501, "utc_offset": 7.0},
    {"city": "kuala_lumpur", "city_name": "Kuala Lumpur", "airport": "KUL", "lat": 2.7456, "lon": 101.7099, "utc_offset": 8.0},
    {"city": "manila", "city_name": "Manila", "airport": "MNL", "lat": 14.5086, "lon": 121.0198, "utc_offset": 8.0},
    {"city": "sydney", "city_name": "Sydney", "airport": "SYD", "lat": -33.9399, "lon": 151.1753, "utc_offset": 10.0},
    {"city": "melbourne", "city_name": "Melbourne", "airport": "MEL", "lat": -37.6690, "lon": 144.8410, "utc_offset": 10.0},
    {"city": "toronto", "city_name": "Toronto", "airport": "YYZ", "lat": 43.6777, "lon": -79.6248, "utc_offset": -5.0},
    {"city": "sao_paulo", "city_name": "Sao Paulo", "airport": "GRU", "lat": -23.4356, "lon": -46.4731, "utc_offset": -3.0},
    {"city": "mexico_city", "city_name": "Mexico City", "airport": "MEX", "lat": 19.4361, "lon": -99.0719, "utc_offset": -6.0},
    {"city": "johannesburg", "city_name": "Johannesburg", "airport": "JNB", "lat": -26.1392, "lon": 28.2460, "utc_offset": 2.0},
]

AIRLINES = [
    ("AI", "Air India"),
    ("LH", "Lufthansa"),
    ("BA", "British Airways"),
    ("AF", "Air France"),
    ("KL", "KLM"),
    ("EK", "Emirates"),
    ("QR", "Qatar Airways"),
    ("SQ", "Singapore Airlines"),
    ("UA", "United Airlines"),
    ("AA", "American Airlines"),
    ("DL", "Delta Air Lines"),
    ("NH", "All Nippon Airways"),
    ("CX", "Cathay Pacific"),
    ("QF", "Qantas"),
    ("TK", "Turkish Airlines"),
    ("EY", "Etihad Airways"),
    ("VS", "Virgin Atlantic"),
]

COLUMNS = [
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
]


@dataclass(frozen=True)
class FlightTemplate:
    flight_number: str
    airline: str
    depart_hour: int
    depart_minute: int
    duration_minutes: int
    stops: int
    economy_price: int
    business_price: int


def haversine_km(a: dict, b: dict) -> float:
    r = 6371.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def duration_minutes_for(distance_km: float, stops: int) -> int:
    cruise_km_h = 820.0
    block = int(distance_km / cruise_km_h * 60) + 45
    if stops:
        block += 85
    return max(75, block)


def local_depart_to_arrive(
    depart_day: date,
    depart_t: time,
    origin_offset: float,
    dest_offset: float,
    duration_min: int,
) -> tuple[date, str]:
    depart_local = datetime.combine(depart_day, depart_t)
    depart_utc = depart_local - timedelta(hours=origin_offset)
    arrive_utc = depart_utc + timedelta(minutes=duration_min)
    arrive_local = arrive_utc + timedelta(hours=dest_offset)
    return arrive_local.date(), arrive_local.strftime("%H:%M")


def daterange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def build_templates(origin: dict, dest: dict, rng: random.Random) -> list[FlightTemplate]:
    distance = haversine_km(origin, dest)
    templates: list[FlightTemplate] = []
    # Mix of early morning (timeline stress) and later-day departures.
    hours = [6, 7, 8, 10, 12, 14, 16, 18, 20, 22]
    for hour in hours[:FLIGHTS_PER_ROUTE_PER_DAY]:
        airline_code, airline_name = AIRLINES[rng.randrange(len(AIRLINES))]
        flight_number = f"{airline_code}{100 + rng.randint(0, 899)}"
        minute = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
        stops = 1 if distance > 6500 and rng.random() < 0.35 else 0
        duration = duration_minutes_for(distance, stops)
        base = 40 + distance * 0.09
        if rng.random() < 0.04:
            base *= 3.2  # expensive outlier for over-budget evals
        economy = max(49, int(base + rng.randint(-25, 40)))
        business = max(economy + 80, int(economy * 2.4 + rng.randint(0, 120)))
        templates.append(
            FlightTemplate(
                flight_number=flight_number,
                airline=airline_name,
                depart_hour=hour,
                depart_minute=minute,
                duration_minutes=duration,
                stops=stops,
                economy_price=economy,
                business_price=business,
            )
        )
    return templates


def open_writer(path: Path, plain: bool):
    path.parent.mkdir(parents=True, exist_ok=True)
    if plain:
        return path.open("w", newline="", encoding="utf-8")
    return gzip.open(path, "wt", newline="", encoding="utf-8", compresslevel=1)


def write_airports(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["city", "city_name", "airport", "lat", "lon", "utc_offset"],
        )
        writer.writeheader()
        writer.writerows(AIRPORTS)


def generate(flights_path: Path, airports_path: Path, plain: bool) -> int:
    write_airports(airports_path)
    n_airports = len(AIRPORTS)
    n_routes = n_airports * (n_airports - 1)
    n_days = (DATE_END - DATE_START).days + 1
    expected = n_routes * FLIGHTS_PER_ROUTE_PER_DAY * len(CABINS) * n_days
    print(f"airports={n_airports} routes={n_routes} days={n_days}")
    print(f"expected_rows={expected:,}")
    print(f"writing {flights_path}")

    handle = open_writer(flights_path, plain)
    offer_n = 0
    try:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for origin in AIRPORTS:
            for dest in AIRPORTS:
                if origin["airport"] == dest["airport"]:
                    continue
                seed = int(
                    hashlib.md5(f"{origin['airport']}-{dest['airport']}".encode()).hexdigest()[:8],
                    16,
                )
                rng = random.Random(seed)
                templates = build_templates(origin, dest, rng)
                o_city, o_ap, o_off = origin["city"], origin["airport"], origin["utc_offset"]
                d_city, d_ap, d_off = dest["city"], dest["airport"], dest["utc_offset"]
                for depart_day in daterange(DATE_START, DATE_END):
                    day_rng = random.Random(seed ^ depart_day.toordinal())
                    depart_iso = depart_day.isoformat()
                    for tmpl in templates:
                        depart_t = time(tmpl.depart_hour, tmpl.depart_minute)
                        arrive_day, arrive_hhmm = local_depart_to_arrive(
                            depart_day,
                            depart_t,
                            o_off,
                            d_off,
                            tmpl.duration_minutes,
                        )
                        if arrive_day.year != YEAR:
                            # Keep every date in 2026: clamp late Dec overflights to 31 Dec evening.
                            arrive_day = DATE_END
                            arrive_hhmm = "23:55"
                        arrive_iso = arrive_day.isoformat()
                        depart_hhmm = depart_t.strftime("%H:%M")
                        for cabin in CABINS:
                            offer_n += 1
                            price = tmpl.economy_price if cabin == "economy" else tmpl.business_price
                            if cabin == "business":
                                refundable = "yes" if day_rng.random() < 0.82 else "no"
                                seats = day_rng.randint(4, 32)
                            else:
                                refundable = "yes" if day_rng.random() < 0.28 else "no"
                                seats = day_rng.randint(6, 180)
                            writer.writerow(
                                (
                                    f"FLT-{offer_n:08d}",
                                    tmpl.flight_number,
                                    tmpl.airline,
                                    o_city,
                                    o_ap,
                                    d_city,
                                    d_ap,
                                    depart_iso,
                                    depart_hhmm,
                                    arrive_iso,
                                    arrive_hhmm,
                                    tmpl.duration_minutes,
                                    tmpl.stops,
                                    cabin,
                                    price,
                                    seats,
                                    refundable,
                                )
                            )
            print(f"  finished origin {origin['airport']}  rows={offer_n:,}", flush=True)
    finally:
        handle.close()
    return offer_n


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate 2026 flight catalog CSV")
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Write uncompressed CSV (very large). Default is .csv.gz",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default data/flights.csv.gz or data/flights.csv)",
    )
    parser.add_argument(
        "--airports-out",
        type=Path,
        default=root / "data" / "airports.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    default_name = "flights.csv" if args.plain else "flights.csv.gz"
    out = args.out or (root / "data" / default_name)
    n = generate(out, args.airports_out, plain=args.plain)
    print(f"wrote {n:,} rows to {out}")
    print(f"wrote airports to {args.airports_out}")


if __name__ == "__main__":
    main()
