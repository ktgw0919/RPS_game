"""TOURNAMENT judgment engine unit tests (ARCHITECTURE.md §8, Phase 3 Step 3).

Pure functions only: no store, sockets, or clock.
"""

from __future__ import annotations

import pytest

from app.game.engine import RoundOutcome
from app.game.rules.tournament import (
    TournamentPair,
    active_match_pairs,
    build_round_pairs,
    build_tournament_bracket,
    collect_round_winners,
    is_bye,
    judge_tournament_pair,
    next_bracket_round,
    pair_for_player,
    segment_id_for,
    tournament_champion,
)
from app.models import Hand

P = ["a", "b", "c", "d", "e"]


def test_segment_id_format() -> None:
    assert segment_id_for(0, 0) == "r0-p0"
    assert segment_id_for(2, 3) == "r2-p3"


def test_build_round_pairs_even_count() -> None:
    pairs = build_round_pairs(["a", "b", "c", "d"], bracket_round=1)
    assert pairs == (
        TournamentPair(segment_id="r1-p0", players=("a", "b")),
        TournamentPair(segment_id="r1-p1", players=("c", "d")),
    )
    assert all(not is_bye(p) for p in pairs)


def test_build_round_pairs_odd_count_gets_bye() -> None:
    pairs = build_round_pairs(P[:5], bracket_round=0)
    assert pairs == (
        TournamentPair(segment_id="r0-p0", players=("a", "b")),
        TournamentPair(segment_id="r0-p1", players=("c", "d")),
        TournamentPair(segment_id="r0-p2", players=("e",)),
    )
    assert is_bye(pairs[2])
    assert active_match_pairs(pairs) == pairs[:2]


def test_build_tournament_bracket() -> None:
    bracket = build_tournament_bracket(["x", "y", "z"])
    assert bracket.participant_ids == ("x", "y", "z")
    assert len(bracket.first_round) == 2
    assert is_bye(bracket.first_round[1])


@pytest.mark.parametrize(
    ("a_hand", "b_hand", "winner"),
    [
        (Hand.ROCK, Hand.SCISSORS, "a"),
        (Hand.SCISSORS, Hand.PAPER, "a"),
        (Hand.PAPER, Hand.ROCK, "a"),
        (Hand.ROCK, Hand.PAPER, "b"),
    ],
)
def test_judge_pair_decisive(a_hand: Hand, b_hand: Hand, winner: str) -> None:
    outcome = judge_tournament_pair("a", "b", {"a": a_hand, "b": b_hand})
    assert outcome.is_draw is False
    assert outcome.winner_ids == (winner,)
    assert outcome.eliminated_ids == ("b" if winner == "a" else "a",)


def test_judge_pair_same_hand_is_draw() -> None:
    outcome = judge_tournament_pair("a", "b", {"a": Hand.ROCK, "b": Hand.ROCK})
    assert outcome.is_draw is True


def test_judge_pair_non_submitter_loses() -> None:
    outcome = judge_tournament_pair("a", "b", {"a": Hand.ROCK})
    assert outcome == RoundOutcome(is_draw=False, winner_ids=("a",), eliminated_ids=("b",))


def test_judge_pair_no_submissions_is_draw() -> None:
    outcome = judge_tournament_pair("a", "b", {})
    assert outcome.is_draw is True


def test_collect_round_winners_with_bye() -> None:
    pairs = build_round_pairs(P[:5], bracket_round=0)
    outcomes = {
        "r0-p0": RoundOutcome(is_draw=False, winner_ids=("a",), eliminated_ids=("b",)),
        "r0-p1": RoundOutcome(is_draw=False, winner_ids=("d",), eliminated_ids=("c",)),
    }
    winners = collect_round_winners(pairs, outcomes)
    assert winners == ("a", "d", "e")


def test_collect_round_winners_rejects_unresolved_draw() -> None:
    pairs = build_round_pairs(["a", "b"], bracket_round=0)
    with pytest.raises(ValueError, match="draw"):
        collect_round_winners(pairs, {"r0-p0": RoundOutcome(is_draw=True)})


def test_full_tournament_four_players() -> None:
    bracket = build_tournament_bracket(["a", "b", "c", "d"])
    r0 = bracket.first_round
    w0 = collect_round_winners(
        r0,
        {
            "r0-p0": RoundOutcome(is_draw=False, winner_ids=("a",), eliminated_ids=("b",)),
            "r0-p1": RoundOutcome(is_draw=False, winner_ids=("c",), eliminated_ids=("d",)),
        },
    )
    assert w0 == ("a", "c")
    assert tournament_champion(w0) is None

    r1 = next_bracket_round(w0, bracket_round=1)
    assert r1 is not None
    assert r1 == (TournamentPair(segment_id="r1-p0", players=("a", "c")),)

    champion = tournament_champion(
        collect_round_winners(
            r1,
            {
                "r1-p0": RoundOutcome(is_draw=False, winner_ids=("a",), eliminated_ids=("c",)),
            },
        )
    )
    assert champion == "a"


def test_full_tournament_five_players_with_bye() -> None:
    bracket = build_tournament_bracket(P[:5])
    w0 = collect_round_winners(
        bracket.first_round,
        {
            "r0-p0": RoundOutcome(is_draw=False, winner_ids=("a",), eliminated_ids=("b",)),
            "r0-p1": RoundOutcome(is_draw=False, winner_ids=("c",), eliminated_ids=("d",)),
        },
    )
    assert w0 == ("a", "c", "e")

    r1 = next_bracket_round(w0, bracket_round=1)
    assert r1 is not None
    assert r1 == (
        TournamentPair(segment_id="r1-p0", players=("a", "c")),
        TournamentPair(segment_id="r1-p1", players=("e",)),
    )

    w1 = collect_round_winners(
        r1,
        {
            "r1-p0": RoundOutcome(is_draw=False, winner_ids=("a",), eliminated_ids=("c",)),
        },
    )
    assert w1 == ("a", "e")

    r2 = next_bracket_round(w1, bracket_round=2)
    assert r2 is not None
    champion = tournament_champion(
        collect_round_winners(
            r2,
            {
                "r2-p0": RoundOutcome(
                    is_draw=False, winner_ids=("a",), eliminated_ids=("e",)
                ),
            },
        )
    )
    assert champion == "a"


def test_pair_for_player() -> None:
    pairs = build_round_pairs(["a", "b", "c"], bracket_round=0)
    assert pair_for_player(pairs, "b") == pairs[0]
    assert pair_for_player(pairs, "c") == pairs[1]
    assert pair_for_player(pairs, "missing") is None
