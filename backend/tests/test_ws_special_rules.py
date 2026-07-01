"""WS integration tests for special rules (TODO Step R5).

Follows the `test_ws_round.py` pattern: injected sleeps for deterministic
timing, multi-socket setup, and full message-flow assertions. Covers MINORITY
(threshold NORMAL transition), BOSS (scores / winner), and TOURNAMENT (4-player
bracket, pair draw replay, bye).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from fastapi.testclient import TestClient

from tests.test_ws import _join, _recv_until
from tests.test_ws_round import _instant, _never, _tune


@contextmanager
def _special_game(
    client: TestClient,
    names: list[str],
    *,
    config: dict[str, Any],
    round_starts: int = 1,
    settings_limit: int = 15,
    boss_player_index: int | None = None,
) -> Iterator[tuple[str, list[tuple[str, str]], list[Any]]]:
    """Create a room, apply rule config, start the match, drain initial ROUND_START(s)."""
    created = client.post("/rooms", json={"display_name": names[0]}).json()
    code = created["room_code"]
    players: list[tuple[str, str]] = [(created["player_id"], created["player_token"])]
    for name in names[1:]:
        m = client.post(f"/rooms/{code}/players", json={"display_name": name}).json()
        players.append((m["player_id"], m["player_token"]))

    match_config = dict(config)
    if boss_player_index is not None:
        match_config["boss_player_id"] = players[boss_player_index][0]

    with ExitStack() as stack:
        sockets: list[Any] = []
        for _pid, token in players:
            ws = stack.enter_context(client.websocket_connect(f"/ws/rooms/{code}"))
            ws.send_json(_join(token))
            _recv_until(ws, "STATE_SYNC")
            sockets.append(ws)

        host_ws = sockets[0]
        host_ws.send_json({"type": "UPDATE_SETTINGS", "payload": {"config": match_config}, "v": 1})
        _recv_until(host_ws, "SETTINGS_UPDATE", limit=settings_limit)
        host_ws.send_json({"type": "START_GAME", "payload": {}, "v": 1})
        _recv_until(host_ws, "LOBBY_UPDATE")
        for _ in range(round_starts):
            _recv_until(host_ws, "ROUND_START")
        yield code, players, sockets


def _submit(
    ws: Any,
    round_no: int,
    hand: str,
    *,
    segment_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {"round_no": round_no, "hand": hand}
    if segment_id is not None:
        payload["segment_id"] = segment_id
    ws.send_json({"type": "SUBMIT_HAND", "payload": payload, "v": 1})


# ------------------------------------------------------------------ MINORITY
def test_minority_three_player_elimination(client: TestClient) -> None:
    _tune(client, deadline=_never, result_delay=_instant)
    with _special_game(client, ["Alice", "Bob", "Carol"], config={"rule_type": "MINORITY"}) as (
        _code,
        players,
        sockets,
    ):
        host_ws, member_ws, carol_ws = sockets
        _submit(host_ws, 1, "ROCK")
        _submit(member_ws, 1, "ROCK")
        _submit(carol_ws, 1, "PAPER")
        result = _recv_until(host_ws, "ROUND_RESULT")["payload"]
        assert result["alive_player_ids"] == [players[2][0]]
        end = _recv_until(host_ws, "MATCH_END")["payload"]
        assert end["winner_ids"] == [players[2][0]]


def test_minority_draw_replays_same_players(client: TestClient) -> None:
    _tune(client, deadline=_never, result_delay=_instant)
    with _special_game(client, ["Alice", "Bob", "Carol"], config={"rule_type": "MINORITY"}) as (
        _code,
        _players,
        sockets,
    ):
        host_ws, member_ws, carol_ws = sockets
        for ws, hand in zip(
            (host_ws, member_ws, carol_ws), ("ROCK", "PAPER", "SCISSORS"), strict=True
        ):
            _submit(ws, 1, hand)
        result = _recv_until(host_ws, "ROUND_RESULT")["payload"]
        assert result["is_draw"] is True
        assert len(result["alive_player_ids"]) == 3
        nxt = _recv_until(host_ws, "ROUND_START")["payload"]
        assert nxt["round_no"] == 2


def test_minority_threshold_switches_to_normal_finish(client: TestClient) -> None:
    """Five players -> two minority survivors, then NORMAL RPS decides (§8)."""
    _tune(client, deadline=_never, result_delay=_instant)
    names = ["p0", "p1", "p2", "p3", "p4"]
    with _special_game(
        client,
        names,
        config={
            "rule_type": "MINORITY",
            "minority_finish_threshold": 2,
            "minority_finish_timing": "IMMEDIATE",
        },
        settings_limit=25,
    ) as (_code, players, sockets):
        p_ids = [p[0] for p in players]
        for ws, hand in zip(sockets[:3], ("ROCK", "ROCK", "ROCK"), strict=True):
            _submit(ws, 1, hand)
        _submit(sockets[3], 1, "PAPER")
        _submit(sockets[4], 1, "PAPER")
        r1 = _recv_until(sockets[0], "ROUND_RESULT")["payload"]
        assert set(r1["alive_player_ids"]) == {p_ids[3], p_ids[4]}
        assert r1["is_draw"] is False

        _recv_until(sockets[0], "ROUND_START")
        _submit(sockets[3], 2, "SCISSORS")
        _submit(sockets[4], 2, "ROCK")
        r2 = _recv_until(sockets[0], "ROUND_RESULT")["payload"]
        assert r2["winner_ids"] == [p_ids[4]]
        end = _recv_until(sockets[0], "MATCH_END")["payload"]
        assert end["winner_ids"] == [p_ids[4]]


# ---------------------------------------------------------------------- BOSS
def test_boss_scores_and_winner_excludes_boss(client: TestClient) -> None:
    _tune(client, deadline=_never, result_delay=_instant)
    with _special_game(
        client,
        ["Boss", "Alice", "Bob"],
        config={"rule_type": "BOSS"},
        boss_player_index=0,
    ) as (_code, players, sockets):
        boss_ws, alice_ws, bob_ws = sockets
        boss_id, alice_id, _bob_id = players[0][0], players[1][0], players[2][0]
        _submit(boss_ws, 1, "ROCK")
        _submit(alice_ws, 1, "PAPER")
        _submit(bob_ws, 1, "SCISSORS")
        result = _recv_until(boss_ws, "ROUND_RESULT")["payload"]
        assert result["hands"][boss_id] == "ROCK"
        assert result["winner_ids"] == [alice_id]
        assert boss_id not in result["alive_player_ids"]
        assert result["scores"] == {alice_id: 1}
        end = _recv_until(boss_ws, "MATCH_END")["payload"]
        assert end["winner_ids"] == [alice_id]
        assert end["scores"] == {alice_id: 1}
        assert boss_id not in end["scores"]


# ---------------------------------------------------------------- TOURNAMENT
def test_tournament_four_player_bracket(client: TestClient) -> None:
    _tune(client, deadline=_never, result_delay=_instant)
    with _special_game(
        client,
        ["A", "B", "C", "D"],
        config={"rule_type": "TOURNAMENT"},
        round_starts=2,
    ) as (_code, players, sockets):
        a_ws, b_ws, c_ws, d_ws = sockets
        a_id, _b_id, c_id, _d_id = (p[0] for p in players)
        _submit(a_ws, 1, "ROCK", segment_id="r0-p0")
        _submit(b_ws, 1, "SCISSORS", segment_id="r0-p0")
        r0 = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert r0["segment_id"] == "r0-p0"
        assert r0["winner_ids"] == [a_id]

        _submit(c_ws, 1, "PAPER", segment_id="r0-p1")
        _submit(d_ws, 1, "ROCK", segment_id="r0-p1")
        r1 = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert r1["segment_id"] == "r0-p1"
        assert r1["winner_ids"] == [c_id]

        final_start = _recv_until(a_ws, "ROUND_START")["payload"]
        assert final_start["segment_id"] == "r1-p0"
        assert set(final_start["alive_player_ids"]) == {a_id, c_id}

        _submit(a_ws, 2, "ROCK", segment_id="r1-p0")
        _submit(c_ws, 2, "SCISSORS", segment_id="r1-p0")
        final = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert final["winner_ids"] == [a_id]
        end = _recv_until(a_ws, "MATCH_END")["payload"]
        assert end["winner_ids"] == [a_id]


def test_tournament_pair_draw_replays_segment(client: TestClient) -> None:
    _tune(client, deadline=_never, result_delay=_instant)
    with _special_game(
        client,
        ["A", "B", "C", "D"],
        config={"rule_type": "TOURNAMENT"},
        round_starts=2,
    ) as (_code, _players, sockets):
        a_ws, b_ws, c_ws, d_ws = sockets
        _submit(a_ws, 1, "ROCK", segment_id="r0-p0")
        _submit(b_ws, 1, "ROCK", segment_id="r0-p0")
        draw = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert draw["segment_id"] == "r0-p0"
        assert draw["is_draw"] is True

        replay = _recv_until(a_ws, "ROUND_START")["payload"]
        assert replay["segment_id"] == "r0-p0"
        assert replay["round_no"] == 2

        _submit(a_ws, 2, "ROCK", segment_id="r0-p0")
        _submit(b_ws, 2, "SCISSORS", segment_id="r0-p0")
        win = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert win["is_draw"] is False
        assert win["winner_ids"] == [_players[0][0]]

        _submit(c_ws, 1, "PAPER", segment_id="r0-p1")
        _submit(d_ws, 1, "SCISSORS", segment_id="r0-p1")
        _recv_until(a_ws, "ROUND_RESULT")


def test_tournament_three_player_bye_advances(client: TestClient) -> None:
    """Odd count: bye holder skips ROUND_START in stage 0 (§8)."""
    _tune(client, deadline=_never, result_delay=_instant)
    with _special_game(
        client,
        ["A", "B", "C"],
        config={"rule_type": "TOURNAMENT"},
        round_starts=1,
    ) as (_code, players, sockets):
        a_ws, b_ws, c_ws = sockets
        a_id, _b_id, c_id = (p[0] for p in players)
        _submit(a_ws, 1, "ROCK", segment_id="r0-p0")
        _submit(b_ws, 1, "SCISSORS", segment_id="r0-p0")
        r0 = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert r0["winner_ids"] == [a_id]

        final_start = _recv_until(a_ws, "ROUND_START")["payload"]
        assert final_start["segment_id"] == "r1-p0"
        assert set(final_start["alive_player_ids"]) == {a_id, c_id}

        _submit(a_ws, 2, "PAPER", segment_id="r1-p0")
        _submit(c_ws, 2, "SCISSORS", segment_id="r1-p0")
        final = _recv_until(a_ws, "ROUND_RESULT")["payload"]
        assert final["winner_ids"] == [c_id]
        end = _recv_until(a_ws, "MATCH_END")["payload"]
        assert end["winner_ids"] == [c_id]
