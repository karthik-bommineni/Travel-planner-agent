"""Shared SQLite catalog path. Repo root is two levels above this module."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB = REPO_ROOT / "data" / "catalog.sqlite"
_LEGACY_DB = REPO_ROOT / "data" / "flights.sqlite"


def catalog_db_path() -> Path:
    override = os.environ.get("CATALOG_DB")
    if override:
        return Path(override)
    if _DEFAULT_DB.exists():
        return _DEFAULT_DB
    if _LEGACY_DB.exists():
        return _LEGACY_DB
    return _DEFAULT_DB


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or catalog_db_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run: python scripts/build_flights_db.py"
        )
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
