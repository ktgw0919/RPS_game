"""REST API tests for `GET /rooms/{code}/matches` (ARCHITECTURE.md §3.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.match_history import MatchHistoryRepository
from app.models import RuleType

NOW = datetime(2026, 6, 29, 8, 0, 0, tzinfo=UTC)


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self._sort_field: str | None = None
        self._sort_dir = -1

    def sort(self, field: str, direction: int) -> _FakeCursor:
        self._sort_field = field
        self._sort_dir = direction
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        docs = list(self._docs)
        if self._sort_field:
            docs.sort(key=lambda d: d[self._sort_field], reverse=self._sort_dir == -1)
        if length is None:
            return docs
        return docs[:length]


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    async def insert_one(self, doc: dict[str, Any]) -> None:
        self.docs.append(doc)

    def find(self, query: dict[str, Any]) -> _FakeCursor:
        room_code = query.get("room_code")
        filtered = [d for d in self.docs if d.get("room_code") == room_code]
        return _FakeCursor(filtered)


def _history_repo_with_docs(*docs: dict[str, Any]) -> MatchHistoryRepository:
    from unittest.mock import MagicMock

    collection = _FakeCollection()
    collection.docs.extend(docs)
    mock_db = MagicMock()
    mock_db.__getitem__.return_value = collection
    return MatchHistoryRepository(mock_db)


def _match_doc(
    *,
    match_id: str,
    room_code: str = "ABCD",
    ended_at: datetime = NOW,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "room_code": room_code,
        "match_id": match_id,
        "rule_type": RuleType.NORMAL.value,
        "players": [
            {"player_id": "p1", "display_name": "Alice", "is_cpu": False},
            {"player_id": "p2", "display_name": "Bob", "is_cpu": False},
        ],
        "winner_ids": ["p1"],
        "scores": {"p1": 1, "p2": 0},
        "started_at": started_at or ended_at - timedelta(minutes=1),
        "ended_at": ended_at,
    }


@pytest.fixture()
def history_client(client: TestClient) -> TestClient:
    docs = [
        _match_doc(match_id="m-new", ended_at=NOW),
        _match_doc(match_id="m-old", ended_at=NOW - timedelta(hours=1)),
    ]
    client.app.state.match_history = _history_repo_with_docs(*docs)
    return client


def test_list_room_matches_returns_newest_first(history_client: TestClient) -> None:
    resp = history_client.get("/rooms/ABCD/matches")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["room_code"] == "ABCD"
    assert data["has_more"] is False
    assert [m["match_id"] for m in data["matches"]] == ["m-new", "m-old"]
    entry = data["matches"][0]
    assert entry["rule_type"] == "NORMAL"
    assert entry["winner_ids"] == ["p1"]
    assert entry["scores"] == {"p1": 1, "p2": 0}
    assert entry["started_at"].endswith("Z")
    assert entry["ended_at"].endswith("Z")
    assert entry["players"][0]["display_name"] == "Alice"


def test_list_room_matches_case_insensitive_code(history_client: TestClient) -> None:
    resp = history_client.get("/rooms/abcd/matches")
    assert resp.status_code == 200
    assert resp.json()["room_code"] == "ABCD"


def test_list_room_matches_has_more(history_client: TestClient) -> None:
    docs = [
        _match_doc(match_id=f"m{i}", ended_at=NOW - timedelta(minutes=i)) for i in range(3)
    ]
    history_client.app.state.match_history = _history_repo_with_docs(*docs)
    resp = history_client.get("/rooms/ABCD/matches?limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["matches"]) == 2
    assert data["has_more"] is True


def test_list_room_matches_independent_of_live_room(client: TestClient) -> None:
    """History is returned even when the in-memory room does not exist."""
    client.app.state.match_history = _history_repo_with_docs(
        _match_doc(match_id="ghost-room", room_code="WXYZ"),
    )
    resp = client.get("/rooms/WXYZ/matches")
    assert resp.status_code == 200
    assert resp.json()["matches"][0]["match_id"] == "ghost-room"


def test_list_room_matches_invalid_code(client: TestClient) -> None:
    resp = client.get("/rooms/AB1D/matches")
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_PAYLOAD"


def test_list_room_matches_invalid_limit(client: TestClient) -> None:
    resp = client.get("/rooms/ABCD/matches?limit=0")
    assert resp.status_code == 422


def test_list_room_matches_service_unavailable(client: TestClient) -> None:
    client.app.state.match_history = MatchHistoryRepository(None)
    resp = client.get("/rooms/ABCD/matches")
    assert resp.status_code == 503
    assert resp.json()["code"] == "SERVICE_UNAVAILABLE"
