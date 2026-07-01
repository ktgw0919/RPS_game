"""WS wiring for special-rule runtime integration Step R1 (ARCHITECTURE.md §4.2 / §8)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import MatchState, RuleType
from tests.test_ws import _add_member, _create_room, _join, _recv_until


def _set_boss_config(client: TestClient, code: str, host_token: str, boss_id: str) -> None:
    with client.websocket_connect(f"/ws/rooms/{code}") as ws:
        ws.send_json(_join(host_token))
        _recv_until(ws, "STATE_SYNC")
        ws.send_json(
            {
                "type": "UPDATE_SETTINGS",
                "payload": {
                    "config": {"rule_type": "BOSS", "boss_player_id": boss_id},
                },
                "v": 1,
            }
        )
        _recv_until(ws, "SETTINGS_UPDATE")


def test_boss_start_without_boss_is_rejected(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    member = _add_member(client, code)
    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as _member_ws:
            _member_ws.send_json(_join(member["player_token"]))
            _recv_until(_member_ws, "STATE_SYNC")

            host_ws.send_json(
                {
                    "type": "UPDATE_SETTINGS",
                    "payload": {"config": {"rule_type": "BOSS"}},
                    "v": 1,
                }
            )
            _recv_until(host_ws, "SETTINGS_UPDATE")

            host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
            err = _recv_until(host_ws, "ERROR")["payload"]
            assert err["code"] == "START_CONDITION_UNMET"
            assert "boss" in err["message"].lower()


def test_boss_start_copies_boss_player_id_to_match(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    member = _add_member(client, code)
    _set_boss_config(client, code, created["player_token"], created["player_id"])

    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as member_ws:
            member_ws.send_json(_join(member["player_token"]))
            _recv_until(member_ws, "STATE_SYNC")

            host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
            _recv_until(host_ws, "LOBBY_UPDATE")

            host_ws.send_json(_join(created["player_token"]))
            snap = _recv_until(host_ws, "STATE_SYNC")["payload"]
            assert snap["match"]["boss_player_id"] == created["player_id"]


def test_submit_hand_rejects_segment_id_for_normal(client: TestClient) -> None:
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
            round_no = int(_recv_until(host_ws, "ROUND_START")["payload"]["round_no"])

            host_ws.send_json(
                {
                    "type": "SUBMIT_HAND",
                    "payload": {"round_no": round_no, "hand": "ROCK", "segment_id": "r0-p0"},
                    "v": 1,
                }
            )
            assert _recv_until(host_ws, "ERROR")["payload"]["code"] == "INVALID_STATE"


def test_boss_leave_clears_nomination(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    member = _add_member(client, code)
    _set_boss_config(client, code, created["player_token"], created["player_id"])

    with client.websocket_connect(f"/ws/rooms/{code}") as boss_ws:
        boss_ws.send_json(_join(created["player_token"]))
        _recv_until(boss_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as member_ws:
            member_ws.send_json(_join(member["player_token"]))
            _recv_until(member_ws, "STATE_SYNC")

            boss_ws.send_json({"type": "LEAVE", "payload": {}, "v": 1})
            _recv_until(member_ws, "PLAYER_LEFT")
            cfg = _recv_until(member_ws, "SETTINGS_UPDATE")["payload"]["config"]
            assert cfg["boss_player_id"] is None


def test_return_to_lobby_applies_minority_defer_normal(client: TestClient) -> None:
    created = _create_room(client)
    code = created["room_code"]
    member = _add_member(client, code)
    third = _add_member(client, code, "Carol")
    store = client.app.state.store  # type: ignore[attr-defined]

    with client.websocket_connect(f"/ws/rooms/{code}") as host_ws:
        host_ws.send_json(_join(created["player_token"]))
        _recv_until(host_ws, "STATE_SYNC")
        with client.websocket_connect(f"/ws/rooms/{code}") as member_ws:
            member_ws.send_json(_join(member["player_token"]))
            _recv_until(member_ws, "STATE_SYNC")
            with client.websocket_connect(f"/ws/rooms/{code}") as third_ws:
                third_ws.send_json(_join(third["player_token"]))
                _recv_until(third_ws, "STATE_SYNC")

                host_ws.send_json(
                    {
                        "type": "UPDATE_SETTINGS",
                        "payload": {"config": {"rule_type": "MINORITY"}},
                        "v": 1,
                    }
                )
                _recv_until(host_ws, "SETTINGS_UPDATE")

                host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
                _recv_until(host_ws, "LOBBY_UPDATE")
                _recv_until(host_ws, "ROUND_START")

                room = store.get_room(code)
                assert room is not None and room.match is not None
                room.match.state = MatchState.MATCH_END
                room.match.minority_defer_normal_next_match = True

                host_ws.send_json({"type": "RETURN_TO_LOBBY", "payload": {}, "v": 1})
                lobby = _recv_until(host_ws, "LOBBY_UPDATE")["payload"]
                assert lobby["config"]["rule_type"] == "NORMAL"

                room = store.get_room(code)
                assert room is not None
                assert room.config.rule_type is RuleType.NORMAL
