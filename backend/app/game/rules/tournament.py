"""Tournament rule judgment and bracket logic (ARCHITECTURE.md §8).

Pure, side-effect-free domain logic for single-elimination 1v1 tournaments.
Participants are paired each bracket stage; odd counts receive a bye. Each
active pair is identified by ``segment_id`` for parallel round messages (§4).
Pair judging is head-to-head; draws replay within the pair only (§8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.game.engine import RoundOutcome
from app.models import Hand

# RPS cycle (same as game/engine.py).
_BEATS: dict[Hand, Hand] = {
    Hand.ROCK: Hand.SCISSORS,
    Hand.SCISSORS: Hand.PAPER,
    Hand.PAPER: Hand.ROCK,
}


@dataclass(frozen=True)
class TournamentPair:
    """One bracket slot: either a 1v1 match or a bye (single player)."""

    segment_id: str
    players: tuple[str, ...]


@dataclass(frozen=True)
class TournamentBracket:
    """Initial single-elimination bracket snapshot (stored on ``Match.bracket``)."""

    participant_ids: tuple[str, ...]
    first_round: tuple[TournamentPair, ...]


def segment_id_for(bracket_round: int, pair_index: int) -> str:
    """Stable segment id for WS round messages (ARCHITECTURE.md §4)."""
    return f"r{bracket_round}-p{pair_index}"


def is_bye(pair: TournamentPair) -> bool:
    return len(pair.players) == 1


def build_round_pairs(
    participant_ids: Sequence[str], bracket_round: int
) -> tuple[TournamentPair, ...]:
    """Pair participants for one bracket stage; trailing odd player gets a bye (§8)."""
    ids = list(participant_ids)
    pairs: list[TournamentPair] = []
    pair_index = 0
    i = 0
    while i < len(ids):
        if i + 1 < len(ids):
            pairs.append(
                TournamentPair(
                    segment_id=segment_id_for(bracket_round, pair_index),
                    players=(ids[i], ids[i + 1]),
                )
            )
            i += 2
        else:
            pairs.append(
                TournamentPair(
                    segment_id=segment_id_for(bracket_round, pair_index),
                    players=(ids[i],),
                )
            )
            i += 1
        pair_index += 1
    return tuple(pairs)


def build_tournament_bracket(participant_ids: Sequence[str]) -> TournamentBracket:
    """Create the opening bracket from set S at ``START_GAME`` (§8)."""
    ordered = tuple(participant_ids)
    return TournamentBracket(
        participant_ids=ordered,
        first_round=build_round_pairs(ordered, bracket_round=0),
    )


def active_match_pairs(pairs: Sequence[TournamentPair]) -> tuple[TournamentPair, ...]:
    """Pairs that require a 1v1 round (excludes byes)."""
    return tuple(p for p in pairs if not is_bye(p))


def pair_for_player(pairs: Sequence[TournamentPair], player_id: str) -> TournamentPair | None:
    """Find the pair (or bye slot) containing ``player_id``."""
    for pair in pairs:
        if player_id in pair.players:
            return pair
    return None


def _beats(attacker: Hand, defender: Hand) -> bool:
    return _BEATS[attacker] is defender


def judge_tournament_pair(
    player_a: str,
    player_b: str,
    submissions: Mapping[str, Hand],
) -> RoundOutcome:
    """Judge one 1v1 tournament pair (ARCHITECTURE.md §8).

    Same hand -> draw (pair-only replay). Different hands -> RPS winner.
    A lone submitter wins; no submissions -> draw (§7).
    """
    hand_a = submissions.get(player_a)
    hand_b = submissions.get(player_b)

    if hand_a is None and hand_b is None:
        return RoundOutcome(is_draw=True)
    if hand_a is None:
        return RoundOutcome(is_draw=False, winner_ids=(player_b,), eliminated_ids=(player_a,))
    if hand_b is None:
        return RoundOutcome(is_draw=False, winner_ids=(player_a,), eliminated_ids=(player_b,))
    if hand_a == hand_b:
        return RoundOutcome(is_draw=True)
    if _beats(hand_a, hand_b):
        return RoundOutcome(is_draw=False, winner_ids=(player_a,), eliminated_ids=(player_b,))
    return RoundOutcome(is_draw=False, winner_ids=(player_b,), eliminated_ids=(player_a,))


def collect_round_winners(
    pairs: Sequence[TournamentPair],
    outcomes_by_segment: Mapping[str, RoundOutcome],
) -> tuple[str, ...]:
    """Advance winners (including bye holders) after a bracket stage resolves.

    Every non-bye pair must have a decisive ``outcomes_by_segment`` entry.
    """
    winners: list[str] = []
    for pair in pairs:
        if is_bye(pair):
            winners.append(pair.players[0])
            continue
        outcome = outcomes_by_segment[pair.segment_id]
        if outcome.is_draw:
            msg = f"pair {pair.segment_id} is still a draw"
            raise ValueError(msg)
        winners.extend(outcome.winner_ids)
    return tuple(winners)


def tournament_champion(advancing: Sequence[str]) -> str | None:
    """Return the champion when exactly one player remains, else ``None``."""
    if len(advancing) == 1:
        return advancing[0]
    return None


def next_bracket_round(
    winners: Sequence[str], bracket_round: int
) -> tuple[TournamentPair, ...] | None:
    """Build the next stage from ``winners``, or ``None`` when the champion is set."""
    if len(winners) <= 1:
        return None
    return build_round_pairs(winners, bracket_round)
