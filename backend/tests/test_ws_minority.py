"""WS integration tests for MINORITY rule (TODO Step R2)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from fastapi.testclient import TestClient

from tests.test_ws import _join, _recv_until
from tests.test_ws_round import _instant, _never, _tune


@contextmanager
def _start_minority_game(
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
                "payload": {"config": {"rule_type": "MINORITY"}},
                "v": 1,
            }
        )
        _recv_until(host_ws, "SETTINGS_UPDATE")
        host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
        _recv_until(host_ws, "LOBBY_UPDATE")
        _recv_until(host_ws, "ROUND_START")
        yield code, players, sockets


def test_minority_match_eliminates_to_one_winner(client: TestClient) -> None:
    _tune(client, deadline=_never, result_delay=_instant)
    with _start_minority_game(client, ["Alice", "Bob", "Carol"]) as (_code, players, sockets):
        host_ws, member_ws, carol_ws = sockets
        round_no = 1
        # ROCK x2, PAPER x1 -> minority PAPER (Carol) wins.
        host_ws.send_json(
            {"type": "SUBMIT_HAND", "payload": {"round_no": round_no, "hand": "ROCK"}, "v": 1}
        )
        member_ws.send_json(
            {"type": "SUBMIT_HAND", "payload": {"round_no": round_no, "hand": "ROCK"}, "v": 1}
        )
        carol_ws.send_json(
            {"type": "SUBMIT_HAND", "payload": {"round_no": round_no, "hand": "PAPER"}, "v": 1}
        )
        result = _recv_until(host_ws, "ROUND_RESULT")
        assert result["payload"]["alive_player_ids"] == [players[2][0]]
        end = _recv_until(host_ws, "MATCH_END")
        assert end["payload"]["winner_ids"] == [players[2][0]]


def test_minority_draw_replays_same_players(client: TestClient) -> None:
    _tune(client, deadline=_never, result_delay=_instant)
    with _start_minority_game(client, ["Alice", "Bob", "Carol"]) as (_code, _players, sockets):
        host_ws, member_ws, carol_ws = sockets
        round_no = 1
        for ws, hand in zip(
            (host_ws, member_ws, carol_ws), ("ROCK", "PAPER", "SCISSORS"), strict=True
        ):
            ws.send_json(
                {"type": "SUBMIT_HAND", "payload": {"round_no": round_no, "hand": hand}, "v": 1}
            )
        result = _recv_until(host_ws, "ROUND_RESULT")
        assert result["payload"]["is_draw"] is True
        assert len(result["payload"]["alive_player_ids"]) == 3
        nxt = _recv_until(host_ws, "ROUND_START")
        assert nxt["payload"]["round_no"] == 2
