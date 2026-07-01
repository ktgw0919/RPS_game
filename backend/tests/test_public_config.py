"""Tests for public client config endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings


def test_public_config_returns_allow_cpu(client: TestClient) -> None:
    response = client.get("/config")
    assert response.status_code == 200
    assert response.json() == {"allow_cpu": True}


def test_public_config_when_cpu_disabled(client: TestClient) -> None:
    client.app.state.settings = Settings(  # type: ignore[attr-defined]
        db_url="mongodb://localhost:27017",
        db_name="rps_test",
        allow_cpu=False,
    )
    response = client.get("/config")
    assert response.status_code == 200
    assert response.json() == {"allow_cpu": False}
