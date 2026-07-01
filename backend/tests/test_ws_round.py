"""Round-loop WS integration tests (ARCHITECTURE.md §4/§6/§7/§7.1/§8).

Timing is made deterministic by injecting the round runner's sleeps (no wall
clock): the round deadline either blocks forever (so submissions drive judging)
or is gated by a threading.Event the test fires; the AUTO result-display delay is
made instant. See `core/round_runner.py`.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from fastapi.testclient import TestClient


# -------------------------------------------------------------------- helpers
async def _never(_seconds: float) -> None:
    await asyncio.Event().wait()  # cancelled on early-finish / shutdown


async def _instant(_seconds: float) -> None:
    return None


def _gated(event: threading.Event) -> Any:
    async def sleep(_seconds: float) -> None:
        while not event.is_set():
            await asyncio.sleep(0.005)

    return sleep


def _tune(client: TestClient, *, deadline: Any = _never, result_delay: Any = _instant) -> None:
    runner = client.app.state.round_runner  # type: ignore[attr-defined]
    runner._deadline_sleep = deadline
    runner._result_delay_sleep = result_delay


def _join(token: str) -> dict[str, Any]:
    return {"type": "JOIN", "payload": {"token": token}, "v": 1}


def _submit(ws: Any, round_no: int, hand: str) -> None:
    ws.send_json({"type": "SUBMIT_HAND", "payload": {"round_no": round_no, "hand": hand}, "v": 1})


def _recv_until(ws: Any, msg_type: str, limit: int = 25) -> dict[str, Any]:
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == msg_type:
            return msg  # type: ignore[no-any-return]
    raise AssertionError(f"did not receive {msg_type} within {limit} messages")


def _round_no(ws: Any) -> int:
    return int(_recv_until(ws, "ROUND_START")["payload"]["round_no"])


@contextmanager
def _game(
    client: TestClient, names: list[str], config: dict[str, Any] | None = None
) -> Iterator[tuple[str, list[tuple[str, str]], list[Any]]]:
    """Create a room with `names`, start the match, and yield (code, players, sockets)."""
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

        host = sockets[0]
        if config is not None:
            host.send_json({"type": "UPDATE_SETTINGS", "payload": {"config": config}, "v": 1})
            _recv_until(host, "SETTINGS_UPDATE")

        host.send_json({"type": "START_GAME", "payload": {}, "v": 1})
        yield code, players, sockets


# ---------------------------------------------------------------------- tests
def test_early_finish_decisive_emits_round_result_and_match_end(client: TestClient) -> None:
    _tune(client)
    with _game(client, ["Host", "Bob"]) as (_code, players, sockets):
        host, bob = sockets
        (host_id, _), (bob_id, _) = players
        rn = _round_no(host)
        _round_no(bob)

        _submit(host, rn, "ROCK")
        _submit(bob, rn, "SCISSORS")  # all submitted -> early finish

        result = _recv_until(host, "ROUND_RESULT")["payload"]
        assert result["is_draw"] is False
        assert result["winner_ids"] == [host_id]
        assert set(result["eliminated_player_ids"]) == {bob_id}
        assert result["hands"] == {host_id: "ROCK", bob_id: "SCISSORS"}
        assert result["scores"] == {}

        end = _recv_until(host, "MATCH_END")["payload"]
        assert end["reason"] == "DECIDED"
        assert end["winner_ids"] == [host_id]


def test_submission_update_reports_progress(client: TestClient) -> None:
    _tune(client)
    with _game(client, ["Host", "Bob"]) as (_code, players, sockets):
        host, bob = sockets
        (host_id, _), _ = players
        rn = _round_no(host)
        _round_no(bob)

        _submit(host, rn, "ROCK")
        upd = _recv_until(host, "SUBMISSION_UPDATE")["payload"]
        assert upd["submitted_player_ids"] == [host_id]
        assert upd["expected_count"] == 2


def test_only_one_round_result_per_round(client: TestClient) -> None:
    # Judge-exactly-once: both submit (early finish); the cancelled deadline must
    # not produce a second ROUND_RESULT for the same round.
    _tune(client)
    with _game(client, ["Host", "Bob"]) as (_code, _players, sockets):
        host, bob = sockets
        rn = _round_no(host)
        _round_no(bob)
        _submit(host, rn, "ROCK")
        _submit(bob, rn, "SCISSORS")

        seen_results = 0
        for _ in range(8):
            msg = host.receive_json()
            if msg["type"] == "ROUND_RESULT":
                seen_results += 1
            if msg["type"] == "MATCH_END":
                break
        assert seen_results == 1


def test_submit_after_judge_is_invalid_state(client: TestClient) -> None:
    _tune(client)
    with _game(client, ["Host", "Bob"]) as (_code, _players, sockets):
        host, bob = sockets
        rn = _round_no(host)
        _round_no(bob)
        _submit(host, rn, "ROCK")
        _submit(bob, rn, "SCISSORS")
        _recv_until(host, "MATCH_END")
        # Match is over; a late submission is rejected.
        _submit(host, rn, "PAPER")
        assert _recv_until(host, "ERROR")["payload"]["code"] == "INVALID_STATE"


def test_spectator_submit_is_not_alive(client: TestClient) -> None:
    # Joining mid-game enters as a spectator (§6); a spectator's hand is NOT_ALIVE.
    _tune(client)
    created = client.post("/rooms", json={"display_name": "Host"}).json()
    code = created["room_code"]
    bob = client.post(f"/rooms/{code}/players", json={"display_name": "Bob"}).json()

    with ExitStack() as stack:
        host = stack.enter_context(client.websocket_connect(f"/ws/rooms/{code}"))
        host.send_json(_join(created["player_token"]))
        _recv_until(host, "STATE_SYNC")
        bws = stack.enter_context(client.websocket_connect(f"/ws/rooms/{code}"))
        bws.send_json(_join(bob["player_token"]))
        _recv_until(bws, "STATE_SYNC")

        host.send_json({"type": "START_GAME", "payload": {}, "v": 1})
        rn = _round_no(host)  # guarantees the room is IN_GAME

        # Carol joins after start -> spectator.
        carol = client.post(f"/rooms/{code}/players", json={"display_name": "Carol"}).json()
        cws = stack.enter_context(client.websocket_connect(f"/ws/rooms/{code}"))
        cws.send_json(_join(carol["player_token"]))
        _recv_until(cws, "STATE_SYNC")
        _submit(cws, rn, "ROCK")
        assert _recv_until(cws, "ERROR")["payload"]["code"] == "NOT_ALIVE"


def test_draw_replays_next_round(client: TestClient) -> None:
    _tune(client)
    with _game(client, ["Host", "Bob"], config={"max_draw_rounds": 5}) as (_c, _p, sockets):
        host, bob = sockets
        rn = _round_no(host)
        _round_no(bob)
        _submit(host, rn, "ROCK")
        _submit(bob, rn, "ROCK")  # 1 kind -> draw

        result = _recv_until(host, "ROUND_RESULT")["payload"]
        assert result["is_draw"] is True
        assert result["round_no"] == rn
        # AUTO advance -> a fresh round with the next number.
        assert _round_no(host) == rn + 1


def test_draw_cap_ends_match(client: TestClient) -> None:
    _tune(client)
    with _game(client, ["Host", "Bob"], config={"max_draw_rounds": 1}) as (_c, _p, sockets):
        host, bob = sockets
        rn = _round_no(host)
        _round_no(bob)
        _submit(host, rn, "PAPER")
        _submit(bob, rn, "PAPER")  # draw -> reaches cap (1)

        assert _recv_until(host, "ROUND_RESULT")["payload"]["is_draw"] is True
        end = _recv_until(host, "MATCH_END")["payload"]
        assert end["reason"] == "DRAW_MAX_ROUNDS"
        assert end["winner_ids"] == []


def test_deadline_eliminates_non_submitter(client: TestClient) -> None:
    fire = threading.Event()
    _tune(client, deadline=_gated(fire))
    with _game(client, ["Host", "Bob", "Carol"]) as (_c, players, sockets):
        host, bob, carol = sockets
        (host_id, _), (bob_id, _), (carol_id, _) = players
        rn = _round_no(host)
        _round_no(bob)
        _round_no(carol)

        _submit(host, rn, "ROCK")
        _submit(bob, rn, "SCISSORS")  # Carol does not submit (2/3)
        # Drain the submission updates, then trip the deadline.
        fire.set()

        result = _recv_until(host, "ROUND_RESULT")["payload"]
        assert result["is_draw"] is False
        assert result["winner_ids"] == [host_id]
        assert carol_id in result["eliminated_player_ids"]
        assert bob_id in result["eliminated_player_ids"]
        # ELIMINATION reduced to a single survivor.
        end = _recv_until(host, "MATCH_END")["payload"]
        assert end["reason"] == "DECIDED"
        assert end["winner_ids"] == [host_id]


def test_manual_advance_waits_for_host_next_round(client: TestClient) -> None:
    _tune(client)
    cfg = {"round_advance_mode": "MANUAL", "max_draw_rounds": 5}
    with _game(client, ["Host", "Bob"], config=cfg) as (_c, _p, sockets):
        host, bob = sockets
        rn = _round_no(host)
        _round_no(bob)
        _submit(host, rn, "ROCK")
        _submit(bob, rn, "ROCK")  # draw -> waits for NEXT_ROUND (MANUAL)
        assert _recv_until(host, "ROUND_RESULT")["payload"]["is_draw"] is True

        # Non-host NEXT_ROUND is rejected.
        bob.send_json({"type": "NEXT_ROUND", "payload": {}, "v": 1})
        assert _recv_until(bob, "ERROR")["payload"]["code"] == "NOT_HOST"

        # Host NEXT_ROUND advances to the next round.
        host.send_json({"type": "NEXT_ROUND", "payload": {}, "v": 1})
        assert _round_no(host) == rn + 1


def test_manual_next_round_wrong_timing_is_invalid_state(client: TestClient) -> None:
    _tune(client)
    cfg = {"round_advance_mode": "MANUAL"}
    with _game(client, ["Host", "Bob"], config=cfg) as (_c, _p, sockets):
        host, _bob = sockets
        _round_no(host)
        # Still COLLECTING (no submissions judged yet) -> NEXT_ROUND is invalid.
        host.send_json({"type": "NEXT_ROUND", "payload": {}, "v": 1})
        assert _recv_until(host, "ERROR")["payload"]["code"] == "INVALID_STATE"


def test_single_round_mode_ends_after_first_decisive(client: TestClient) -> None:
    _tune(client)
    cfg = {"normal_end_mode": "SINGLE_ROUND"}
    with _game(client, ["Host", "Bob", "Carol"], config=cfg) as (_c, players, sockets):
        host, bob, carol = sockets
        (host_id, _), (bob_id, _), (carol_id, _) = players
        rn = _round_no(host)
        _round_no(bob)
        _round_no(carol)

        _submit(host, rn, "ROCK")
        _submit(bob, rn, "ROCK")
        _submit(carol, rn, "SCISSORS")  # 2 kinds -> ROCK side wins

        result = _recv_until(host, "ROUND_RESULT")["payload"]
        assert result["is_draw"] is False
        assert set(result["winner_ids"]) == {host_id, bob_id}
        assert result["eliminated_player_ids"] == [carol_id]

        end = _recv_until(host, "MATCH_END")["payload"]
        assert end["reason"] == "DECIDED"
        assert set(end["winner_ids"]) == {host_id, bob_id}


def test_elimination_needs_two_rounds_for_three_players(client: TestClient) -> None:
    """ELIMINATION: one loser per decisive round until a single survivor remains."""
    _tune(client)
    with _game(client, ["Host", "Bob", "Carol"]) as (_c, players, sockets):
        host, bob, carol = sockets
        (host_id, _), (bob_id, _), (carol_id, _) = players

        rn1 = _round_no(host)
        _round_no(bob)
        _round_no(carol)
        _submit(host, rn1, "ROCK")
        _submit(bob, rn1, "SCISSORS")
        _submit(carol, rn1, "PAPER")  # 3 kinds -> draw

        r1 = _recv_until(host, "ROUND_RESULT")["payload"]
        assert r1["is_draw"] is True
        assert set(r1["alive_player_ids"]) == {host_id, bob_id, carol_id}

        rn2 = _round_no(host)
        _round_no(bob)
        _round_no(carol)
        _submit(host, rn2, "ROCK")
        _submit(bob, rn2, "ROCK")
        _submit(carol, rn2, "SCISSORS")  # ROCK beats SCISSORS -> Carol out

        r2 = _recv_until(host, "ROUND_RESULT")["payload"]
        assert r2["is_draw"] is False
        assert carol_id in r2["eliminated_player_ids"]
        assert set(r2["alive_player_ids"]) == {host_id, bob_id}

        rn3 = _round_no(host)
        _round_no(bob)
        _submit(host, rn3, "ROCK")
        _submit(bob, rn3, "SCISSORS")

        r3 = _recv_until(host, "ROUND_RESULT")["payload"]
        assert r3["winner_ids"] == [host_id]
        end = _recv_until(host, "MATCH_END")["payload"]
        assert end["winner_ids"] == [host_id]


def test_three_kinds_submission_is_draw(client: TestClient) -> None:
    _tune(client)
    with _game(client, ["Host", "Bob", "Carol"]) as (_c, players, sockets):
        host, bob, carol = sockets
        (host_id, _), (bob_id, _), (carol_id, _) = players
        rn = _round_no(host)
        _round_no(bob)
        _round_no(carol)
        _submit(host, rn, "ROCK")
        _submit(bob, rn, "SCISSORS")
        _submit(carol, rn, "PAPER")

        result = _recv_until(host, "ROUND_RESULT")["payload"]
        assert result["is_draw"] is True
        assert set(result["alive_player_ids"]) == {host_id, bob_id, carol_id}
        assert result["eliminated_player_ids"] == []


def test_no_submissions_at_deadline_replays_draw(client: TestClient) -> None:
    """§7 safety: zero submitters at deadline -> draw, same members replay."""
    fire = threading.Event()
    _tune(client, deadline=_gated(fire))
    with _game(client, ["Host", "Bob"], config={"max_draw_rounds": 5}) as (_c, _p, sockets):
        host, bob = sockets
        rn = _round_no(host)
        _round_no(bob)
        fire.set()

        result = _recv_until(host, "ROUND_RESULT")["payload"]
        assert result["is_draw"] is True
        assert result["round_no"] == rn
        assert result["hands"] == {}
        assert _round_no(host) == rn + 1


def test_stale_round_no_submit_is_invalid_state(client: TestClient) -> None:
    _tune(client)
    with _game(client, ["Host", "Bob"]) as (_c, _p, sockets):
        host, bob = sockets
        rn = _round_no(host)
        _round_no(bob)
        _submit(host, rn + 99, "ROCK")
        assert _recv_until(host, "ERROR")["payload"]["code"] == "INVALID_STATE"


def test_resubmit_overwrites_hand_before_judge(client: TestClient) -> None:
    _tune(client)
    with _game(client, ["Host", "Bob"]) as (_c, players, sockets):
        host, bob = sockets
        (host_id, _), (bob_id, _) = players
        rn = _round_no(host)
        _round_no(bob)
        _submit(host, rn, "SCISSORS")
        _submit(host, rn, "ROCK")  # overwrite before judge
        _submit(bob, rn, "SCISSORS")

        result = _recv_until(host, "ROUND_RESULT")["payload"]
        assert result["hands"][host_id] == "ROCK"
        assert result["winner_ids"] == [host_id]


def test_match_end_persists_history(client: TestClient) -> None:
    saved: list[tuple[str, str]] = []

    class RecordingHistory:
        async def save_finished_match(self, room: object, match: object) -> None:
            from app.models import Match, Room

            assert isinstance(room, Room)
            assert isinstance(match, Match)
            saved.append((room.room_code, match.match_id))

    recorder = RecordingHistory()
    client.app.state.match_history = recorder  # type: ignore[attr-defined]
    client.app.state.round_runner._match_history = recorder  # type: ignore[attr-defined]

    _tune(client)
    with _game(client, ["Host", "Bob"]) as (code, players, sockets):
        host, bob = sockets
        rn = _round_no(host)
        _round_no(bob)
        _submit(host, rn, "ROCK")
        _submit(bob, rn, "SCISSORS")
        _recv_until(host, "MATCH_END")

    assert len(saved) == 1
    assert saved[0][0] == code
    match = client.app.state.store.get_room(code).match  # type: ignore[attr-defined]
    assert match is not None
    assert saved[0][1] == match.match_id
