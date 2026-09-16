from pathlib import Path

import pytest

from app.tools.db import catalog_db_path

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def catalog_path() -> Path:
    path = catalog_db_path()
    if not path.exists():
        pytest.skip(f"catalog missing at {path}; build SQLite first")
    return path
