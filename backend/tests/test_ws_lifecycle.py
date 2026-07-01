"""Lifecycle WS integration tests (ARCHITECTURE.md §6/§10).

Covers the operator-visible lifecycle flows end-to-end over the WS endpoint:
- a WAITING host `LEAVE` hands off immediately (HOST_CHANGED + LOBBY_UPDATE)
- `RETURN_TO_LOBBY` merges spectators and prunes un-returned ghosts (PLAYER_LEFT)
- an idle room is swept to CLOSED with an ERROR(ROOM_CLOSED) notice

The idle case drives the resident sweep deterministically by calling
`sweep_once(now)` on the app loop via the test client's blocking portal, with an
injected `now` far past the idle TTL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.models import ConnectionState, MatchState


def _join(token: str) -> dict[str, Any]:
    return {"type": "JOIN", "payload": {"token": token}, "v": 1}


def _recv_until(ws: Any, msg_type: str, limit: int = 12) -> dict[str, Any]:
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == msg_type:
            return msg  # type: ignore[no-any-return]
    raise AssertionError(f"did not receive {msg_type} within {limit} messages")


def _create(client: TestClient, name: str = "Host") -> dict[str, Any]:
    return client.post("/rooms", json={"display_name": name}).json()  # type: ignore[no-any-return]


def _join_rest(client: TestClient, code: str, name: str) -> dict[str, Any]:
    return client.post(f"/rooms/{code}/players", json={"display_name": name}).json()  # type: ignore[no-any-return]


def test_waiting_host_leave_transfers_host(client: TestClient) -> None:
    created = _create(client)
    code = created["room_code"]
    member = _join_rest(client, code, "Bob")

    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as member_ws:
            member_ws.send_json(_join(member["player_token"]))
            _recv_until(member_ws, "STATE_SYNC")

            host_ws.send_json({"type": "LEAVE", "payload": {}, "v": 1})

            changed = _recv_until(member_ws, "HOST_CHANGED")["payload"]
            assert changed["host_player_id"] == member["player_id"]

            lobby = _recv_until(member_ws, "LOBBY_UPDATE")["payload"]
            assert lobby["host_player_id"] == member["player_id"]
            assert [m["player_id"] for m in lobby["members"]] == [member["player_id"]]
            assert lobby["members"][0]["is_host"] is True


def test_return_to_lobby_merges_spectator_and_prunes_ghost(client: TestClient) -> None:
    created = _create(client)
    code = created["room_code"]
    bob = _join_rest(client, code, "Bob")

    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as bob_ws:
            bob_ws.send_json(_join(bob["player_token"]))
            _recv_until(bob_ws, "STATE_SYNC")

            host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
            _recv_until(host_ws, "ROUND_START")

            # Carol joins mid-game -> spectator (§6); connect so she stays in the room.
            carol = _join_rest(client, code, "Carol")
            with client.websocket_connect(f"/ws/rooms/{code}") as carol_ws:
                carol_ws.send_json(_join(carol["player_token"]))
                _recv_until(carol_ws, "STATE_SYNC")

                store = client.app.state.store  # type: ignore[attr-defined]
                room = store.get_room(code)
                # Force the match to MATCH_END and Bob into an un-returned ghost.
                room.match.state = MatchState.MATCH_END
                store.set_connection_state(room, bob["player_id"], ConnectionState.DISCONNECTED)

                host_ws.send_json({"type": "RETURN_TO_LOBBY", "payload": {}, "v": 1})

                left = _recv_until(host_ws, "PLAYER_LEFT")["payload"]
                assert left["player_id"] == bob["player_id"]

                lobby = _recv_until(host_ws, "LOBBY_UPDATE")["payload"]
                ids = {m["player_id"] for m in lobby["members"]}
                assert bob["player_id"] not in ids  # ghost pruned
                assert carol["player_id"] in ids
                carol_view = next(
                    m for m in lobby["members"] if m["player_id"] == carol["player_id"]
                )
                assert carol_view["is_spectator"] is False  # merged into players
                assert room.status.value == "WAITING"
                assert room.match is None


def test_idle_room_sweep_closes_with_room_closed(client: TestClient) -> None:
    created = _create(client)
    code = created["room_code"]

    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")

        store = client.app.state.store  # type: ignore[attr-defined]
        room = store.get_room(code)
        room.last_active_at = datetime(2026, 1, 1, tzinfo=UTC)
        far_future = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=1800 + 60)

        lifecycle = client.app.state.lifecycle  # type: ignore[attr-defined]
        assert client.portal is not None
        client.portal.call(lifecycle.sweep_once, far_future)

        err = _recv_until(host_ws, "ERROR")["payload"]
        assert err["code"] == "ROOM_CLOSED"
        assert room.status.value == "CLOSED"
