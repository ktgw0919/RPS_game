"""Tests for settings loading and fail-fast behavior."""

from __future__ import annotations

import pytest

from app.config import ConfigError, Settings


def test_load_with_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("DB_NAME", "rps")
    settings = Settings.load()
    assert settings.db_url == "mongodb://localhost:27017"
    assert settings.db_name == "rps"
    # Defaults for operational tunables.
    assert settings.allow_cpu is True
    assert settings.room_idle_ttl_sec == 1800
    assert settings.host_transfer_grace_sec == 30


def test_fail_fast_missing_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    # Avoid reading a developer's local .env during this test.
    monkeypatch.setattr("app.config.config", _raising_config)
    with pytest.raises(ConfigError):
        Settings.load()


def test_cors_origins_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("DB_NAME", "rps")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test ")
    settings = Settings.load()
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def _raising_config(key: str, default: object = ..., cast: object = None) -> object:
    if default is ...:
        raise KeyError(key)
    return default
