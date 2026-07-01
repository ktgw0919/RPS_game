"""REST API tests for room create / join / fetch (ARCHITECTURE.md §3.1/§3.2)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _create(client: TestClient, name: str = "Alice") -> dict[str, Any]:
    resp = client.post("/rooms", json={"display_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_room_returns_token_and_view(client: TestClient) -> None:
    data = _create(client)
    assert len(data["room_code"]) == 4
    assert data["player_id"]
    assert data["player_token"]
    room = data["room"]
    assert room["host_player_id"] == data["player_id"]
    assert room["member_count"] == 1
    assert room["capacity"] == 20
    assert room["status"] == "WAITING"
    assert room["config"]["rule_type"] == "NORMAL"
    # The token must never leak into the RoomView.
    assert "token" not in str(room)


def test_join_room_ok(client: TestClient) -> None:
    created = _create(client)
    code = created["room_code"]
    resp = client.post(f"/rooms/{code}/players", json={"display_name": "Bob"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["player_id"] != created["player_id"]
    assert data["player_token"] != created["player_token"]
    assert data["room"]["member_count"] == 2


def test_join_is_case_insensitive(client: TestClient) -> None:
    code = _create(client)["room_code"]
    resp = client.post(f"/rooms/{code.lower()}/players", json={"display_name": "Bob"})
    assert resp.status_code == 201


def test_join_room_not_found(client: TestClient) -> None:
    resp = client.post("/rooms/ZZZZ/players", json={"display_name": "Bob"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "ROOM_NOT_FOUND"


def test_get_room(client: TestClient) -> None:
    code = _create(client)["room_code"]
    resp = client.get(f"/rooms/{code}")
    assert resp.status_code == 200
    assert resp.json()["room"]["room_code"] == code


def test_get_room_not_found(client: TestClient) -> None:
    resp = client.get("/rooms/ZZZZ")
    assert resp.status_code == 404
    assert resp.json()["code"] == "ROOM_NOT_FOUND"


def test_display_name_invalid(client: TestClient) -> None:
    resp = client.post("/rooms", json={"display_name": "   "})
    assert resp.status_code == 422


def test_room_full(client: TestClient) -> None:
    code = _create(client)["room_code"]
    # 1 host already; fill up to capacity (20).
    for i in range(19):
        r = client.post(f"/rooms/{code}/players", json={"display_name": f"P{i}"})
        assert r.status_code == 201
    overflow = client.post(f"/rooms/{code}/players", json={"display_name": "late"})
    assert overflow.status_code == 409
    assert overflow.json()["code"] == "ROOM_FULL"


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
