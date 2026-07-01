"""Match FSM / store unit tests (ARCHITECTURE.md §6, Phase 2 Step 4).

These exercise the state-store transition API directly (no WebSocket), keeping
the FSM deterministic: time is injected via `now`, never read from the clock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.state_store import IllegalMatchTransition, InMemoryGameStateStore
from app.models import (
    ConnectionState,
    CpuStrategy,
    Hand,
    MatchConfig,
    MatchState,
    Player,
    RoomStatus,
    RuleType,
)

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _player(pid: str, **kwargs: Any) -> Player:
    kwargs.setdefault("token", f"tok-{pid}")
    return Player(player_id=pid, display_name=pid, joined_at=NOW, **kwargs)


def _store_with_two() -> tuple[InMemoryGameStateStore, Any]:
    store = InMemoryGameStateStore()
    room = store.create_room(_player("h"))
    store.add_player(room, _player("p2"))
    return store, room


def _started_match(store: InMemoryGameStateStore, room: Any) -> Any:
    return store.start_match(
        room, alive_player_ids=["h", "p2"], config=room.config, match_id="m1", now=NOW
    )


def test_start_match_sets_in_game_and_collecting() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    assert room.status is RoomStatus.IN_GAME
    assert room.match is match
    assert match.state is MatchState.COLLECTING
    assert match.alive_player_ids == ["h", "p2"]
    assert match.scores == {}
    assert match.current_round_no == 0
    assert match.started_at == NOW
    assert room.last_active_at == NOW


def test_full_round_cycle_transitions_are_allowed() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.set_match_state(match, MatchState.JUDGING)
    assert match.state is MatchState.JUDGING
    store.set_match_state(match, MatchState.ROUND_RESULT)
    assert match.state is MatchState.ROUND_RESULT
    # continue -> next round
    store.set_match_state(match, MatchState.COLLECTING)
    assert match.state is MatchState.COLLECTING


def test_match_end_stamps_ended_at() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.set_match_state(match, MatchState.JUDGING)
    store.set_match_state(match, MatchState.ROUND_RESULT)
    end = datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC)
    store.set_match_state(match, MatchState.MATCH_END, now=end)
    assert match.state is MatchState.MATCH_END
    assert match.ended_at == end


@pytest.mark.parametrize("target", [MatchState.ROUND_RESULT, MatchState.MATCH_END])
def test_illegal_transition_from_collecting(target: MatchState) -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    with pytest.raises(IllegalMatchTransition):
        store.set_match_state(match, target)


def test_illegal_transition_from_judging() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.set_match_state(match, MatchState.JUDGING)
    with pytest.raises(IllegalMatchTransition):
        store.set_match_state(match, MatchState.COLLECTING)


def test_no_transition_out_of_match_end() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.set_match_state(match, MatchState.JUDGING)
    store.set_match_state(match, MatchState.ROUND_RESULT)
    store.set_match_state(match, MatchState.MATCH_END, now=NOW)
    for target in (MatchState.COLLECTING, MatchState.JUDGING, MatchState.ROUND_RESULT):
        with pytest.raises(IllegalMatchTransition):
            store.set_match_state(match, target)


def test_set_config_replaces_room_config() -> None:
    store, room = _store_with_two()
    store.set_config(room, MatchConfig(round_time_limit_sec=20, max_draw_rounds=3))
    assert room.config.round_time_limit_sec == 20
    assert room.config.max_draw_rounds == 3


# --------------------------------------------------------------------------
# Step 7/9: round bookkeeping (begin -> submit -> judge -> next/end)
# --------------------------------------------------------------------------
def test_begin_round_opens_fresh_round_and_bumps_number() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    deadline = datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC)
    rnd = store.begin_round(match, round_no=1, deadline_at=deadline)
    assert match.current_round is rnd
    assert match.current_round_no == 1
    assert rnd.deadline_at == deadline
    assert rnd.submissions == {}
    assert rnd.judged_at is None


def test_save_submission_then_judge_marks_round() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.begin_round(match, round_no=1, deadline_at=NOW)
    store.save_submission(match, "h", Hand.ROCK)
    store.save_submission(match, "p2", Hand.SCISSORS)
    assert match.current_round is not None
    assert match.current_round.submissions == {"h": Hand.ROCK, "p2": Hand.SCISSORS}

    store.set_match_state(match, MatchState.JUDGING)
    store.mark_round_judged(match, now=NOW)
    assert match.current_round.judged_at == NOW


def test_submission_overwrite_before_judge() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.begin_round(match, round_no=1, deadline_at=NOW)
    store.save_submission(match, "h", Hand.ROCK)
    store.save_submission(match, "h", Hand.PAPER)
    assert match.current_round is not None
    assert match.current_round.submissions["h"] == Hand.PAPER


def test_set_alive_and_draw_count() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.set_alive(match, ["h"])
    assert match.alive_player_ids == ["h"]
    assert store.increment_draw_count(match) == 1
    assert store.increment_draw_count(match) == 2
    assert match.draw_round_count == 2


def test_finalize_match_records_winners_and_ends() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.set_match_state(match, MatchState.JUDGING)
    store.set_match_state(match, MatchState.ROUND_RESULT)
    end = datetime(2026, 1, 1, 12, 9, 0, tzinfo=UTC)
    store.finalize_match(match, winner_ids=["h"], now=end)
    assert match.state is MatchState.MATCH_END
    assert match.winner_ids == ["h"]
    assert match.ended_at == end


# --------------------------------------------------------------------------
# Step 10: lifecycle store helpers (return_to_lobby / host / roster)
# --------------------------------------------------------------------------
def test_return_to_lobby_merges_spectators_and_drops_ghosts() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.set_match_state(match, MatchState.JUDGING)
    store.set_match_state(match, MatchState.ROUND_RESULT)
    store.set_match_state(match, MatchState.MATCH_END, now=NOW)
    store.add_player(room, _player("spec", is_spectator=True))
    store.set_connection_state(room, "p2", ConnectionState.DISCONNECTED, now=NOW)

    removed = store.return_to_lobby(room)

    assert removed == ["p2"]
    assert room.status is RoomStatus.WAITING
    assert room.match is None
    assert room.members["spec"].is_spectator is False
    assert "p2" not in room.members


def test_set_host_transfers_flag() -> None:
    store, room = _store_with_two()
    store.set_host(room, "p2")
    assert room.host_player_id == "p2"
    assert room.members["h"].is_host is False
    assert room.members["p2"].is_host is True


def test_oldest_connected_human_excludes_cpu() -> None:
    store, room = _store_with_two()
    store.add_player(
        room,
        Player(
            player_id="cpu1",
            token=None,
            display_name="cpu1",
            is_cpu=True,
            cpu_strategy=CpuStrategy.RANDOM,
            joined_at=NOW,  # joined before humans but must not be host candidate
        ),
    )
    assert store.oldest_connected_human_id(room) == "h"
    # When only CPU remains connected, there is no human successor.
    for pid in ("h", "p2"):
        store.set_connection_state(room, pid, ConnectionState.DISCONNECTED, now=NOW)
    assert store.oldest_connected_human_id(room) is None


# --------------------------------------------------------------------------
# Step R0: special-rule match fields and segment/score store API
# --------------------------------------------------------------------------
def test_start_match_normal_initializes_special_rule_defaults() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    assert match.switched_to_normal_finish is False
    assert match.minority_defer_normal_next_match is False
    assert match.tournament_bracket_round == 0
    assert match.tournament_active_pairs == []
    assert match.tournament_segment_rounds == {}
    assert match.boss_player_id is None


def test_start_match_boss_copies_boss_player_id() -> None:
    store, room = _store_with_two()
    store.set_config(room, MatchConfig(rule_type=RuleType.BOSS, boss_player_id="h"))
    match = store.start_match(
        room, alive_player_ids=["h", "p2"], config=room.config, match_id="m-boss", now=NOW
    )
    assert match.rule_type is RuleType.BOSS
    assert match.boss_player_id == "h"


def test_start_match_tournament_builds_active_pairs() -> None:
    store, room = _store_with_two()
    store.add_player(room, _player("p3"))
    store.set_config(room, MatchConfig(rule_type=RuleType.TOURNAMENT))
    match = store.start_match(
        room,
        alive_player_ids=["h", "p2", "p3"],
        config=room.config,
        match_id="m-t",
        now=NOW,
    )
    assert match.tournament_bracket_round == 0
    assert [p.segment_id for p in match.tournament_active_pairs] == ["r0-p0", "r0-p1"]
    assert match.tournament_active_pairs[0].players == ("h", "p2")
    assert match.tournament_active_pairs[1].players == ("p3",)


def test_begin_segment_round_and_submissions() -> None:
    store, room = _store_with_two()
    store.set_config(room, MatchConfig(rule_type=RuleType.TOURNAMENT))
    match = store.start_match(
        room, alive_player_ids=["h", "p2"], config=room.config, match_id="m-seg", now=NOW
    )
    deadline = datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC)
    rnd = store.begin_segment_round(match, "r0-p0", round_no=1, deadline_at=deadline)
    assert match.current_round_no == 1
    assert match.tournament_segment_rounds["r0-p0"] is rnd
    store.save_segment_submission(match, "r0-p0", "h", Hand.ROCK)
    store.save_segment_submission(match, "r0-p0", "p2", Hand.PAPER)
    assert rnd.submissions == {"h": Hand.ROCK, "p2": Hand.PAPER}
    store.mark_segment_judged(match, "r0-p0", now=NOW)
    assert rnd.judged_at == NOW


def test_apply_score_deltas_accumulates() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.apply_score_deltas(match, [("h", 1), ("p2", 2)])
    store.apply_score_deltas(match, [("h", 1)])
    assert match.scores == {"h": 2, "p2": 2}


def test_set_minority_defer_normal_next_match() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.set_minority_defer_normal_next_match(match)
    assert match.minority_defer_normal_next_match is True


def test_set_switched_to_normal_finish() -> None:
    store, room = _store_with_two()
    match = _started_match(store, room)
    store.set_switched_to_normal_finish(match)
    assert match.switched_to_normal_finish is True
    store.set_switched_to_normal_finish(match, value=False)
    assert match.switched_to_normal_finish is False


def test_disconnect_stamps_disconnected_at() -> None:
    store, room = _store_with_two()
    when = datetime(2026, 1, 1, 12, 2, 0, tzinfo=UTC)
    store.set_connection_state(room, "p2", ConnectionState.DISCONNECTED, now=when)
    assert room.members["p2"].disconnected_at == when
    store.set_connection_state(room, "p2", ConnectionState.CONNECTED, now=when)
    assert room.members["p2"].disconnected_at is None
    assert room.members["p2"].last_seen_at == when
