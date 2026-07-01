"""WebSocket resilience integration tests (ARCHITECTURE.md §3/§4/§11).

Covers reconnect restoration and last-wins replacement during an active match.
Lobby-only cases live in `test_ws.py`; round-loop cases in `test_ws_round.py`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_ws_round import _join, _recv_until, _round_no, _submit, _tune


def test_reconnect_mid_game_restores_authoritative_snapshot(client: TestClient) -> None:
    """Same-token JOIN during COLLECTING returns a full STATE_SYNC reset (§4)."""
    _tune(client)
    created = client.post("/rooms", json={"display_name": "Host"}).json()
    code = created["room_code"]
    bob = client.post(f"/rooms/{code}/players", json={"display_name": "Bob"}).json()
    url = f"/ws/rooms/{code}"

    with client.websocket_connect(url) as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(url) as bob_ws:
            bob_ws.send_json(_join(bob["player_token"]))
            _recv_until(bob_ws, "STATE_SYNC")
            host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
            rn = _round_no(host_ws)
            _round_no(bob_ws)
            _submit(host_ws, rn, "ROCK")

    # Host reconnects mid-round; STATE_SYNC must restore match + submission state.
    with client.websocket_connect(url) as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        snap = _recv_until(host_ws, "STATE_SYNC")["payload"]
        assert snap["you"]["player_id"] == created["player_id"]
        assert snap["you"]["connection_state"] == "CONNECTED"
        assert snap["room"]["status"] == "IN_GAME"
        match = snap["match"]
        assert match is not None
        assert match["state"] == "COLLECTING"
        assert match["current_round_no"] == rn
        assert match["my_submitted"] is True
        assert match["deadline_at"] is not None
        assert match["deadline_at"].endswith("Z")
        assert set(match["alive_player_ids"]) == {created["player_id"], bob["player_id"]}
        assert "token" not in str(snap)


def test_session_replaced_during_in_game(client: TestClient) -> None:
    """Last-wins applies during a match: old socket gets SESSION_REPLACED (§3)."""
    _tune(client)
    created = client.post("/rooms", json={"display_name": "Host"}).json()
    code = created["room_code"]
    bob = client.post(f"/rooms/{code}/players", json={"display_name": "Bob"}).json()
    url = f"/ws/rooms/{code}"
    token = created["player_token"]

    with client.websocket_connect(url) as host_old:
        host_old.send_json(_join(token))
        _recv_until(host_old, "STATE_SYNC")
        _recv_until(host_old, "LOBBY_UPDATE")
        with client.websocket_connect(url) as bob_ws:
            bob_ws.send_json(_join(bob["player_token"]))
            _recv_until(bob_ws, "STATE_SYNC")
            host_old.send_json({"type": "START_GAME", "payload": {}, "v": 1})
            _round_no(host_old)
            _round_no(bob_ws)

            with client.websocket_connect(url) as host_new:
                host_new.send_json(_join(token))
                snap = _recv_until(host_new, "STATE_SYNC")["payload"]
                assert snap["room"]["status"] == "IN_GAME"
                assert snap["match"] is not None
                assert snap["match"]["state"] == "COLLECTING"

                replaced = host_old.receive_json()
                assert replaced["type"] == "ERROR"
                assert replaced["payload"]["code"] == "SESSION_REPLACED"


def test_disconnect_marks_disconnected_then_reconnect_restores(client: TestClient) -> None:
    """Disconnect -> DISCONNECTED in roster; reconnect -> CONNECTED again (§7)."""
    _tune(client)
    created = client.post("/rooms", json={"display_name": "Host"}).json()
    code = created["room_code"]
    bob = client.post(f"/rooms/{code}/players", json={"display_name": "Bob"}).json()
    url = f"/ws/rooms/{code}"

    with client.websocket_connect(url) as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(url) as bob_ws:
            bob_ws.send_json(_join(bob["player_token"]))
            _recv_until(bob_ws, "STATE_SYNC")
            host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
            _round_no(host_ws)
            _round_no(bob_ws)

    # Bob disconnected; host should see DISCONNECTED in LOBBY_UPDATE.
    with client.websocket_connect(url) as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        lobby = _recv_until(host_ws, "LOBBY_UPDATE")["payload"]
        bob_view = next(m for m in lobby["members"] if m["player_id"] == bob["player_id"])
        assert bob_view["connection_state"] == "DISCONNECTED"

    # Bob reconnects.
    with client.websocket_connect(url) as bob_ws:
        bob_ws.send_json(_join(bob["player_token"]))
        snap = _recv_until(bob_ws, "STATE_SYNC")["payload"]
        assert snap["you"]["connection_state"] == "CONNECTED"
