"""WebSocket JOIN/auth integration tests (ARCHITECTURE.md §3/§4, Phase 2 Step 1).

Covers the handshake contract:
- connect -> JOIN -> STATE_SYNC snapshot (+ roster LOBBY_UPDATE broadcast)
- first message not JOIN / unknown token -> ERROR(INVALID_TOKEN) + close
- connecting to a missing room -> ERROR(ROOM_NOT_FOUND) + close
- reconnect with the same token re-binds to the existing player
- a live duplicate connection replaces the old one (last-wins, SESSION_REPLACED)

Uses the Starlette test client (sync), which drives the ASGI app in-process.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _create_room(client: TestClient, name: str = "Alice") -> dict[str, Any]:
    resp = client.post("/rooms", json={"display_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _join(token: str) -> dict[str, Any]:
    return {"type": "JOIN", "payload": {"token": token}, "v": 1}


def _add_member(client: TestClient, code: str, name: str = "Bob") -> dict[str, Any]:
    resp = client.post(f"/rooms/{code}/players", json={"display_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _recv_until(ws: Any, msg_type: str, limit: int = 6) -> dict[str, Any]:
    """Read frames until one of `msg_type` arrives (skipping unrelated ones)."""
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == msg_type:
            return msg  # type: ignore[no-any-return]
    raise AssertionError(f"did not receive {msg_type} within {limit} messages")


def test_join_returns_state_sync_then_lobby_update(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json(_join(created["player_token"]))

        snapshot = ws.receive_json()
        assert snapshot["type"] == "STATE_SYNC"
        assert snapshot["v"] == 1
        payload = snapshot["payload"]
        assert payload["you"]["player_id"] == created["player_id"]
        assert payload["you"]["connection_state"] == "CONNECTED"
        assert payload["room"]["room_code"] == code
        assert payload["match"] is None
        assert len(payload["members"]) == 1
        # server_now is UTC ISO8601 with millisecond precision and trailing Z.
        assert payload["server_now"].endswith("Z")
        # No token must ever leak into the snapshot.
        assert "token" not in str(payload)

        # A connection-state change broadcasts the authoritative roster.
        roster = ws.receive_json()
        assert roster["type"] == "LOBBY_UPDATE"
        assert roster["payload"]["host_player_id"] == created["player_id"]


def test_first_message_not_join_is_rejected(client: TestClient) -> None:
    code = _create_room(client)["room_code"]
    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json({"type": "PING", "payload": {}, "v": 1})
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["payload"]["code"] == "INVALID_TOKEN"


def test_unknown_token_is_rejected(client: TestClient) -> None:
    code = _create_room(client)["room_code"]
    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json(_join("definitely-not-a-valid-token"))
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["payload"]["code"] == "INVALID_TOKEN"


def test_missing_token_payload_is_rejected(client: TestClient) -> None:
    code = _create_room(client)["room_code"]
    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json({"type": "JOIN", "payload": {}, "v": 1})
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["payload"]["code"] == "INVALID_TOKEN"


def test_connect_to_missing_room_is_rejected(client: TestClient) -> None:
    with client.websocket_connect("/ws/rooms/ZZZZ") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "ERROR"
        assert msg["payload"]["code"] == "ROOM_NOT_FOUND"


def test_reconnect_rebinds_to_same_player(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    token = created["player_token"]
    url = f"/ws/rooms/{code}"

    with client.websocket_connect(url) as ws:
        ws.send_json(_join(token))
        assert ws.receive_json()["type"] == "STATE_SYNC"

    # Reconnecting with the same token must re-bind, not create a new player.
    with client.websocket_connect(url) as ws:
        ws.send_json(_join(token))
        again = ws.receive_json()
        assert again["type"] == "STATE_SYNC"
        assert again["payload"]["you"]["player_id"] == created["player_id"]
        assert again["payload"]["you"]["connection_state"] == "CONNECTED"
        assert again["payload"]["room"]["member_count"] == 1


def test_duplicate_connection_replaces_old_session(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    token = created["player_token"]
    url = f"/ws/rooms/{code}"

    with client.websocket_connect(url) as ws_old:
        ws_old.send_json(_join(token))
        assert ws_old.receive_json()["type"] == "STATE_SYNC"
        assert ws_old.receive_json()["type"] == "LOBBY_UPDATE"

        with client.websocket_connect(url) as ws_new:
            ws_new.send_json(_join(token))
            assert ws_new.receive_json()["type"] == "STATE_SYNC"

            # The old socket is replaced (last-wins) with SESSION_REPLACED.
            replaced = ws_old.receive_json()
            assert replaced["type"] == "ERROR"
            assert replaced["payload"]["code"] == "SESSION_REPLACED"


# --------------------------------------------------------------------------
# Step 5: heartbeat + envelope I/O
# --------------------------------------------------------------------------
def test_ping_returns_pong(client: TestClient) -> None:
    created = _create_room(client)
    with client.websocket_connect(f"/ws/rooms/{created['room_code']}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        ws.send_json({"type": "PING", "payload": {}, "v": 1})
        assert _recv_until(ws, "PONG")["type"] == "PONG"


def test_unknown_type_keeps_connection_open(client: TestClient) -> None:
    created = _create_room(client)
    with client.websocket_connect(f"/ws/rooms/{created['room_code']}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        ws.send_json({"type": "NOPE", "payload": {}, "v": 1})
        assert _recv_until(ws, "ERROR")["payload"]["code"] == "INVALID_PAYLOAD"
        # The connection stays open: a following PING still gets a PONG.
        ws.send_json({"type": "PING", "payload": {}, "v": 1})
        assert _recv_until(ws, "PONG")["type"] == "PONG"


def test_version_mismatch_is_invalid_payload(client: TestClient) -> None:
    created = _create_room(client)
    with client.websocket_connect(f"/ws/rooms/{created['room_code']}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        ws.send_json({"type": "PING", "payload": {}, "v": 2})
        assert _recv_until(ws, "ERROR")["payload"]["code"] == "INVALID_PAYLOAD"


# --------------------------------------------------------------------------
# Step 6: host settings + start
# --------------------------------------------------------------------------
def test_non_host_update_settings_is_rejected(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    member = _add_member(client, code)
    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as member_ws:
            member_ws.send_json(_join(member["player_token"]))
            _recv_until(member_ws, "STATE_SYNC")
            member_ws.send_json(
                {
                    "type": "UPDATE_SETTINGS",
                    "payload": {"config": {"round_time_limit_sec": 20}},
                    "v": 1,
                }
            )
            assert _recv_until(member_ws, "ERROR")["payload"]["code"] == "NOT_HOST"


def test_update_settings_broadcasts_to_everyone(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    member = _add_member(client, code)
    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as member_ws:
            member_ws.send_json(_join(member["player_token"]))
            _recv_until(member_ws, "STATE_SYNC")

            host_ws.send_json(
                {
                    "type": "UPDATE_SETTINGS",
                    "payload": {"config": {"round_time_limit_sec": 20, "max_draw_rounds": 3}},
                    "v": 1,
                }
            )
            host_cfg = _recv_until(host_ws, "SETTINGS_UPDATE")["payload"]["config"]
            member_cfg = _recv_until(member_ws, "SETTINGS_UPDATE")["payload"]["config"]
            assert host_cfg["round_time_limit_sec"] == 20
            assert host_cfg["max_draw_rounds"] == 3
            assert member_cfg["round_time_limit_sec"] == 20


def test_update_settings_out_of_range_is_invalid_payload(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        # 7 is in [5,60] but not a multiple of 5 (§9 step rule) -> rejected.
        ws.send_json(
            {
                "type": "UPDATE_SETTINGS",
                "payload": {"config": {"round_time_limit_sec": 7}},
                "v": 1,
            }
        )
        assert _recv_until(ws, "ERROR")["payload"]["code"] == "INVALID_PAYLOAD"


def test_start_game_requires_minimum_players(client: TestClient) -> None:
    created = _create_room(client)
    with client.websocket_connect(f"/ws/rooms/{created['room_code']}") as ws:
        ws.send_json(_join(created["player_token"]))
        _recv_until(ws, "STATE_SYNC")
        ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
        assert _recv_until(ws, "ERROR")["payload"]["code"] == "START_CONDITION_UNMET"


def test_start_game_moves_room_to_in_game(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    member = _add_member(client, code)
    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as member_ws:
            member_ws.send_json(_join(member["player_token"]))
            _recv_until(member_ws, "STATE_SYNC")

            host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
            _recv_until(host_ws, "LOBBY_UPDATE")

            # Re-sync (JOIN) to read the authoritative IN_GAME snapshot.
            host_ws.send_json(_join(created["player_token"]))
            snap = _recv_until(host_ws, "STATE_SYNC")["payload"]
            assert snap["room"]["status"] == "IN_GAME"
            assert snap["match"] is not None
            assert snap["match"]["state"] == "COLLECTING"
            assert set(snap["match"]["alive_player_ids"]) == {
                created["player_id"],
                member["player_id"],
            }


def test_update_settings_after_start_is_invalid_state(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    member = _add_member(client, code)
    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as member_ws:
            member_ws.send_json(_join(member["player_token"]))
            _recv_until(member_ws, "STATE_SYNC")

            host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
            _recv_until(host_ws, "LOBBY_UPDATE")

            host_ws.send_json(
                {
                    "type": "UPDATE_SETTINGS",
                    "payload": {"config": {"round_time_limit_sec": 20}},
                    "v": 1,
                }
            )
            assert _recv_until(host_ws, "ERROR")["payload"]["code"] == "INVALID_STATE"
