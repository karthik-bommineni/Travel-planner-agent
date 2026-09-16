"""Load data/hotels.csv into the catalog SQLite DB (does not rebuild flights)."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

CREATE_HOTELS = """
CREATE TABLE hotels (
    hotel_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    city_name TEXT NOT NULL,
    stars INTEGER NOT NULL,
    cost_per_day INTEGER NOT NULL,
    rooms_available INTEGER NOT NULL,
    amenities TEXT NOT NULL,
    check_in TEXT NOT NULL,
    check_out TEXT NOT NULL
);
"""


def load_hotels(conn: sqlite3.Connection, csv_path: Path) -> int:
    conn.execute("DROP TABLE IF EXISTS hotels")
    conn.execute(CREATE_HOTELS)
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = [
            (
                r["hotel_id"],
                r["name"],
                r["city"],
                r["city_name"],
                int(r["stars"]),
                int(r["cost_per_day"]),
                int(r["rooms_available"]),
                r["amenities"],
                r["check_in"],
                r["check_out"],
            )
            for r in csv.DictReader(f)
        ]
    conn.executemany("INSERT INTO hotels VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.execute("CREATE INDEX idx_hotels_city ON hotels(city)")
    conn.execute("CREATE INDEX idx_hotels_city_stars ON hotels(city, stars)")
    conn.commit()
    return len(rows)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=root / "data" / "catalog.sqlite")
    parser.add_argument("--csv", type=Path, default=root / "data" / "hotels.csv")
    args = parser.parse_args()
    if not args.csv.exists():
        sys.exit(f"missing {args.csv}; run python scripts/generate_hotels.py")
    if not args.db.exists():
        sys.exit(f"missing {args.db}; run python scripts/build_flights_db.py first")
    conn = sqlite3.connect(args.db)
    try:
        n = load_hotels(conn, args.csv)
    finally:
        conn.close()
    print(f"hotels: {n:,} rows in {args.db}")


if __name__ == "__main__":
    main()
