"""Load data/flights.csv.gz (and airports.csv) into SQLite for indexed search.

Usage (from repo root):
    python scripts/build_flights_db.py

Creates data/catalog.sqlite with tables `airports` and `flights`, plus an index on
(origin_airport, destination_airport, depart_date, cabin).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import sqlite3
import sys
from pathlib import Path

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

INT_COLS = {"duration_minutes", "stops", "price_usd", "seats_available"}
BATCH = 20_000

CREATE_FLIGHTS = """
CREATE TABLE flights (
    offer_id TEXT PRIMARY KEY,
    flight_number TEXT NOT NULL,
    airline TEXT NOT NULL,
    origin_city TEXT NOT NULL,
    origin_airport TEXT NOT NULL,
    destination_city TEXT NOT NULL,
    destination_airport TEXT NOT NULL,
    depart_date TEXT NOT NULL,
    depart_time TEXT NOT NULL,
    arrive_date TEXT NOT NULL,
    arrive_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    stops INTEGER NOT NULL,
    cabin TEXT NOT NULL,
    price_usd INTEGER NOT NULL,
    seats_available INTEGER NOT NULL,
    is_refundable TEXT NOT NULL
);
"""

INSERT_SQL = (
    "INSERT INTO flights VALUES (" + ",".join("?" for _ in COLUMNS) + ")"
)


def load_airports(conn: sqlite3.Connection, path: Path) -> None:
    conn.execute("DROP TABLE IF EXISTS airports")
    conn.execute(
        """
        CREATE TABLE airports (
            city TEXT NOT NULL,
            city_name TEXT NOT NULL,
            airport TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            utc_offset REAL NOT NULL
        )
        """
    )
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    conn.executemany(
        "INSERT INTO airports VALUES (?,?,?,?,?,?)",
        [
            (
                r["city"],
                r["city_name"],
                r["airport"],
                float(r["lat"]),
                float(r["lon"]),
                float(r["utc_offset"]),
            )
            for r in rows
        ],
    )
    conn.execute("CREATE INDEX idx_airports_city ON airports(city)")
    print(f"airports: {len(rows)} rows", flush=True)


def row_tuple(raw: dict) -> tuple:
    vals = []
    for col in COLUMNS:
        v = raw[col]
        vals.append(int(v) if col in INT_COLS else v)
    return tuple(vals)


def load_flights(conn: sqlite3.Connection, gz_path: Path) -> int:
    conn.execute("DROP TABLE IF EXISTS flights")
    conn.execute(CREATE_FLIGHTS)
    n = 0
    batch: list[tuple] = []
    with gzip.open(gz_path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            batch.append(row_tuple(raw))
            if len(batch) >= BATCH:
                conn.executemany(INSERT_SQL, batch)
                n += len(batch)
                batch.clear()
                if n % 500_000 == 0:
                    conn.commit()
                    print(f"  inserted {n:,} flights", flush=True)
        if batch:
            conn.executemany(INSERT_SQL, batch)
            n += len(batch)
    conn.commit()
    print("creating indexes...", flush=True)
    conn.execute(
        """
        CREATE INDEX idx_flights_search
        ON flights(origin_airport, destination_airport, depart_date, cabin)
        """
    )
    conn.execute(
        """
        CREATE INDEX idx_flights_city_search
        ON flights(origin_city, destination_city, depart_date, cabin)
        """
    )
    conn.commit()
    return n


def build(db_path: Path, flights_gz: Path, airports_csv: Path) -> None:
    if not flights_gz.exists():
        sys.exit(f"missing {flights_gz}")
    if not airports_csv.exists():
        sys.exit(f"missing {airports_csv}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
        for suffix in ("-wal", "-shm"):
            extra = Path(str(db_path) + suffix)
            if extra.exists():
                extra.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -256000")
        load_airports(conn, airports_csv)
        n = load_flights(conn, flights_gz)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        print(f"flights: {n:,} rows")
        print(f"wrote {db_path}")
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description="Build flights SQLite DB from gzip CSV")
    p.add_argument("--db", type=Path, default=root / "data" / "catalog.sqlite")
    p.add_argument("--flights", type=Path, default=root / "data" / "flights.csv.gz")
    p.add_argument("--airports", type=Path, default=root / "data" / "airports.csv")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    build(args.db, args.flights, args.airports)


if __name__ == "__main__":
    main()
