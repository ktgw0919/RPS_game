"""Shared test fixtures.

Required settings are injected via environment variables before the app is
imported (fail-fast otherwise). The app continues even if MongoDB is
unreachable, so these tests run without a live database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("DB_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "rps_test")
os.environ.setdefault("ROOM_CREATE_RATE_MAX", "1000")


@pytest.fixture()
def client() -> Iterator[object]:
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
