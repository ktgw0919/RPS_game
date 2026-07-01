"""WS integration tests for BOSS rule (TODO Step R3)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from fastapi.testclient import TestClient

from tests.test_ws import _join, _recv_until
from tests.test_ws_round import _instant, _never, _tune


@contextmanager
def _start_boss_game(
    client: TestClient, names: list[str], *, boss_index: int = 0
) -> Iterator[tuple[str, list[tuple[str, str]], list[Any]]]:
    created = client.post("/rooms", json={"display_name": names[0]}).json()
    code = created["room_code"]
    players: list[tuple[str, str]] = [(created["player_id"], created["player_token"])]
    for name in names[1:]:
        m = client.post(f"/rooms/{code}/players", json={"display_name": name}).json()
        players.append((m["player_id"], m["player_token"]))

    boss_id = players[boss_index][0]

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
                "payload": {
                    "config": {"rule_type": "BOSS", "boss_player_id": boss_id},
                },
                "v": 1,
            }
        )
        _recv_until(host_ws, "SETTINGS_UPDATE")
        host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
        _recv_until(host_ws, "LOBBY_UPDATE")
        _recv_until(host_ws, "ROUND_START")
        yield code, players, sockets


def test_boss_match_scores_and_excludes_boss_from_alive(client: TestClient) -> None:
    _tune(client, deadline=_never, result_delay=_instant)
    with _start_boss_game(client, ["Boss", "Alice", "Bob"]) as (_code, players, sockets):
        boss_ws, alice_ws, bob_ws = sockets
        boss_id, alice_id, _bob_id = players[0][0], players[1][0], players[2][0]
        round_no = 1
        boss_ws.send_json(
            {"type": "SUBMIT_HAND", "payload": {"round_no": round_no, "hand": "ROCK"}, "v": 1}
        )
        alice_ws.send_json(
            {"type": "SUBMIT_HAND", "payload": {"round_no": round_no, "hand": "PAPER"}, "v": 1}
        )
        bob_ws.send_json(
            {"type": "SUBMIT_HAND", "payload": {"round_no": round_no, "hand": "SCISSORS"}, "v": 1}
        )
        result = _recv_until(boss_ws, "ROUND_RESULT")["payload"]
        assert result["hands"][boss_id] == "ROCK"
        assert result["winner_ids"] == [alice_id]
        assert boss_id not in result["alive_player_ids"]
        assert result["alive_player_ids"] == [alice_id]
        assert result["scores"] == {alice_id: 1}
        end = _recv_until(boss_ws, "MATCH_END")["payload"]
        assert end["winner_ids"] == [alice_id]
        assert end["scores"] == {alice_id: 1}
        assert boss_id not in end["scores"]
