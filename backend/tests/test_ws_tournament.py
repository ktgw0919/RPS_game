"""WS integration tests for TOURNAMENT rule (TODO Step R4)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from fastapi.testclient import TestClient

from tests.test_ws import _join, _recv_until
from tests.test_ws_round import _instant, _never, _tune


@contextmanager
def _start_tournament_game(
    client: TestClient, names: list[str]
) -> Iterator[tuple[str, list[tuple[str, str]], list[Any]]]:
    created = client.post("/rooms", json={"display_name": names[0]}).json()
    code = created["room_code"]
    players: list[tuple[str, str]] = [(created["player_id"], created["player_token"])]
    for name in names[1:]:
        m = client.post(f"/rooms/{code}/players", json={"display_name": name}).json()
        players.append((m["player_id"], m["player_token"]))

    with ExitStack() as stack:
        sockets: list[Any] = []
        for _pid, token in players:
            ws = stack.enter_context(client.websocket_connect(f"/ws/rooms/{code}"))
            ws.send_json(_join(token))
            _recv_until(ws, "STATE_SYNC")
            sockets.append(ws)

        host_ws = sockets[0]
        host_ws.send_json(
            {
                "type": "UPDATE_SETTINGS",
                "payload": {"config": {"rule_type": "TOURNAMENT"}},
                "v": 1,
            }
        )
        _recv_until(host_ws, "SETTINGS_UPDATE", limit=15)
        host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
        _recv_until(host_ws, "LOBBY_UPDATE")
        for _ in range(2):
            _recv_until(host_ws, "ROUND_START")
        yield code, players, sockets


def test_tournament_four_player_bracket(client: TestClient) -> None:
    _tune(client, deadline=_never, result_delay=_instant)
    with _start_tournament_game(client, ["A", "B", "C", "D"]) as (_code, players, sockets):
        a_ws, b_ws, c_ws, d_ws = sockets
        a_id, b_id, c_id, d_id = (p[0] for p in players)
        round_no = 1
        a_ws.send_json(
            {
                "type": "SUBMIT_HAND",
                "payload": {"round_no": round_no, "hand": "ROCK", "segment_id": "r0-p0"},
                "v": 1,
            }
        )
        b_ws.send_json(
            {
                "type": "SUBMIT_HAND",
                "payload": {"round_no": round_no, "hand": "SCISSORS", "segment_id": "r0-p0"},
                "v": 1,
            }
        )
        r0 = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert r0["segment_id"] == "r0-p0"
        assert r0["winner_ids"] == [a_id]

        c_ws.send_json(
            {
                "type": "SUBMIT_HAND",
                "payload": {"round_no": round_no, "hand": "PAPER", "segment_id": "r0-p1"},
                "v": 1,
            }
        )
        d_ws.send_json(
            {
                "type": "SUBMIT_HAND",
                "payload": {"round_no": round_no, "hand": "ROCK", "segment_id": "r0-p1"},
                "v": 1,
            }
        )
        r1 = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert r1["segment_id"] == "r0-p1"
        assert r1["winner_ids"] == [c_id]

        final_start = _recv_until(a_ws, "ROUND_START")["payload"]
        assert final_start["segment_id"] == "r1-p0"
        assert set(final_start["alive_player_ids"]) == {a_id, c_id}

        a_ws.send_json(
            {
                "type": "SUBMIT_HAND",
                "payload": {"round_no": 2, "hand": "ROCK", "segment_id": "r1-p0"},
                "v": 1,
            }
        )
        c_ws.send_json(
            {
                "type": "SUBMIT_HAND",
                "payload": {"round_no": 2, "hand": "SCISSORS", "segment_id": "r1-p0"},
                "v": 1,
            }
        )
        final = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert final["winner_ids"] == [a_id]
        end = _recv_until(a_ws, "MATCH_END")["payload"]
        assert end["winner_ids"] == [a_id]
