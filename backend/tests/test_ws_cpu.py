"""CPU WebSocket integration tests (ARCHITECTURE.md §3/§4/§6, Phase 2 Step 13)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.core.constants import ROOM_CAPACITY
from app.models import Hand
from tests.test_ws_round import _game, _instant, _join, _recv_until, _round_no, _submit, _tune


def _add_cpu(ws: Any, *, count: int = 1) -> None:
    ws.send_json({"type": "ADD_CPU", "payload": {"count": count}, "v": 1})


def _tune_cpu(client: TestClient, hand: Hand = Hand.SCISSORS) -> None:
    _tune(client)
    runner = client.app.state.round_runner  # type: ignore[attr-defined]
    runner._cpu_delay_sleep = _instant
    runner._pick_hand = lambda _player: hand


def test_solo_host_and_cpu_play_full_match(client: TestClient) -> None:
    """Solo human + CPU can start, submit, judge, and end the match."""
    _tune_cpu(client, Hand.SCISSORS)
    created = client.post("/rooms", json={"display_name": "Host"}).json()
    code = created["room_code"]
    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        _add_cpu(ws)
        _recv_until(ws, "PLAYER_JOINED")
        lobby = _recv_until(ws, "LOBBY_UPDATE")["payload"]
        cpu_id = next(m["player_id"] for m in lobby["members"] if m["is_cpu"])

        ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
        rn = _round_no(ws)
        _submit(ws, rn, "ROCK")  # ROCK beats injected CPU SCISSORS

        result = _recv_until(ws, "ROUND_RESULT")["payload"]
        assert result["winner_ids"] == [created["player_id"]]
        assert cpu_id in result["eliminated_player_ids"]

        end = _recv_until(ws, "MATCH_END")["payload"]
        assert end["reason"] == "DECIDED"
        assert end["winner_ids"] == [created["player_id"]]


def test_add_cpu_when_disabled_returns_cpu_not_allowed(client: TestClient) -> None:
    client.app.state.settings = Settings(  # type: ignore[attr-defined]
        db_url="mongodb://localhost:27017",
        db_name="rps_test",
        allow_cpu=False,
    )
    created = client.post("/rooms", json={"display_name": "Host"}).json()
    with client.websocket_connect(f"/ws/rooms/{created['room_code']}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        _add_cpu(ws)
        assert _recv_until(ws, "ERROR")["payload"]["code"] == "CPU_NOT_ALLOWED"


def test_add_cpu_in_game_is_invalid_state(client: TestClient) -> None:
    _tune(client)
    with _game(client, ["Host", "Bob"]) as (_code, _players, sockets):
        host = sockets[0]
        _add_cpu(host)
        assert _recv_until(host, "ERROR")["payload"]["code"] == "INVALID_STATE"


def test_add_cpu_when_full_returns_room_full(client: TestClient) -> None:
    created = client.post("/rooms", json={"display_name": "Host"}).json()
    code = created["room_code"]
    # Fill remaining slots with REST joins (host already occupies one seat).
    for i in range(ROOM_CAPACITY - 1):
        client.post(f"/rooms/{code}/players", json={"display_name": f"P{i}"})

    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        _add_cpu(ws)
        assert _recv_until(ws, "ERROR")["payload"]["code"] == "ROOM_FULL"


def test_fixed_cpu_plays_scripted_hands(client: TestClient) -> None:
    _tune(client)
    runner = client.app.state.round_runner  # type: ignore[attr-defined]
    runner._cpu_delay_sleep = _instant
    created = client.post("/rooms", json={"display_name": "Host"}).json()
    code = created["room_code"]
    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        ws.send_json(
            {
                "type": "ADD_CPU",
                "payload": {"count": 1, "strategy": "FIXED", "fixed_hands": ["SCISSORS", "PAPER"]},
                "v": 1,
            }
        )
        _recv_until(ws, "PLAYER_JOINED")
        lobby = _recv_until(ws, "LOBBY_UPDATE")["payload"]
        cpu = next(m for m in lobby["members"] if m["is_cpu"])
        assert cpu["cpu_strategy"] == "FIXED"
        assert cpu["cpu_fixed_hands"] == ["SCISSORS", "PAPER"]

        ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
        rn = _round_no(ws)
        _submit(ws, rn, "ROCK")

        result = _recv_until(ws, "ROUND_RESULT")["payload"]
        assert result["winner_ids"] == [created["player_id"]]
        assert cpu["player_id"] in result["eliminated_player_ids"]


def test_remove_cpu_drops_last_cpu(client: TestClient) -> None:
    created = client.post("/rooms", json={"display_name": "Host"}).json()
    code = created["room_code"]
    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        _add_cpu(ws)
        joined = _recv_until(ws, "PLAYER_JOINED")["payload"]["player"]
        cpu_id = joined["player_id"]

        ws.send_json({"type": "REMOVE_CPU", "payload": {}, "v": 1})
        left = _recv_until(ws, "PLAYER_LEFT")["payload"]
        assert left["player_id"] == cpu_id
        lobby = _recv_until(ws, "LOBBY_UPDATE")["payload"]
        assert all(not m["is_cpu"] for m in lobby["members"])
