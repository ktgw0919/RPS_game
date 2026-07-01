"""Game state store abstraction (ARCHITECTURE.md §1/§5/§7.1).

The authoritative live game state is held behind this interface so the
implementation can be swapped later (e.g. a Redis-backed store for horizontal
scale). The MVP uses a single-process in-memory implementation.

Phase 1 only needs room create/lookup/membership; richer operations (matches,
rounds, locks) are layered on in Phase 2 while keeping this interface as the
single access point.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime

from app.core.constants import ROOM_CODE_MAX_GEN_ATTEMPTS
from app.core.security import verify_token
from app.game.rules.tournament import build_tournament_bracket
from app.models import (
    ConnectionState,
    Hand,
    Match,
    MatchConfig,
    MatchState,
    Player,
    Room,
    RoomStatus,
    Round,
    RuleType,
    TournamentPair,
)
from app.utils import generate_room_code, utcnow

# Allowed Match.state transitions (ARCHITECTURE.md §6). MVP: NORMAL only, but the
# table is rule-agnostic. Round progression that drives these transitions
# (timer/submit/judge) is implemented in Phase 2 Steps 7-9.
_MATCH_TRANSITIONS: dict[MatchState, frozenset[MatchState]] = {
    MatchState.COLLECTING: frozenset({MatchState.JUDGING}),
    MatchState.JUDGING: frozenset({MatchState.ROUND_RESULT}),
    MatchState.ROUND_RESULT: frozenset({MatchState.COLLECTING, MatchState.MATCH_END}),
    MatchState.MATCH_END: frozenset(),
}


class RoomCodeExhaustedError(RuntimeError):
    """Raised when a unique room code could not be generated after retries."""


class IllegalMatchTransition(RuntimeError):
    """Raised on a Match.state change that violates the FSM (ARCHITECTURE.md §6)."""


class GameStateStore(ABC):
    """Interface for accessing authoritative live game state."""

    @abstractmethod
    def get_room(self, room_code: str) -> Room | None: ...

    @abstractmethod
    def all_rooms(self) -> list[Room]:
        """Snapshot of all rooms (for the lifecycle sweep, §10)."""

    @abstractmethod
    def create_room(self, host: Player) -> Room:
        """Create a new room with a unique code, with `host` as its only member."""

    @abstractmethod
    def add_player(self, room: Room, player: Player) -> None:
        """Add a player to an existing room and touch its activity timestamp."""

    @abstractmethod
    def get_player(self, room: Room, player_id: str) -> Player | None:
        """Return a member by id, or None."""

    @abstractmethod
    def get_player_by_token(self, room: Room, token: str) -> Player | None:
        """Return the member whose token matches (constant-time), or None.

        Used for WS `JOIN` verification / reconnection re-binding (§3). CPU
        players have no token and never match.
        """

    @abstractmethod
    def set_connection_state(
        self, room: Room, player_id: str, state: ConnectionState, *, now: datetime | None = None
    ) -> None:
        """Update a member's connection state and touch the room (§10).

        Stamps `disconnected_at` on CONNECTED->DISCONNECTED (for ghost TTL / host
        grace) and clears it (refreshing `last_seen_at`) on reconnect.
        """

    @abstractmethod
    def touch_player(self, room: Room, player_id: str, *, now: datetime) -> None:
        """Record liveness for a member's latest inbound frame (heartbeat, §10)."""

    @abstractmethod
    def remove_player(self, room: Room, player_id: str) -> None:
        """Remove a member from the room and touch it (LEAVE / ghost sweep, §6/§10)."""

    @abstractmethod
    def set_host(self, room: Room, player_id: str) -> None:
        """Make `player_id` the host, clearing the previous host's flag (§10)."""

    @abstractmethod
    def oldest_connected_human_id(self, room: Room, *, exclude_id: str | None = None) -> str | None:
        """Oldest CONNECTED human member (host-transfer candidate; CPU excluded, §10)."""

    @abstractmethod
    def close_room(self, room: Room) -> None:
        """Mark the room CLOSED (idle sweep / human-zero, §10)."""

    @abstractmethod
    def return_to_lobby(self, room: Room) -> list[str]:
        """MATCH_END -> WAITING: merge spectators, drop ghosts, clear match (§6).

        Returns the ids of removed DISCONNECTED ghosts (for PLAYER_LEFT).
        """

    @abstractmethod
    def set_config(self, room: Room, config: MatchConfig) -> None:
        """Replace the room's next-match config and touch the room (§9)."""

    @abstractmethod
    def start_match(
        self,
        room: Room,
        *,
        alive_player_ids: list[str],
        config: MatchConfig,
        match_id: str,
        now: datetime,
    ) -> Match:
        """Create a Match in COLLECTING and move the room to IN_GAME (§4.2/§6).

        `alive_player_ids` is the start-condition set S (§4.2). `now` is injected
        for deterministic testing. Calls `init_match_for_rule` before return.
        """

    @abstractmethod
    def init_match_for_rule(self, match: Match, config: MatchConfig) -> None:
        """Initialize rule-specific match fields after `start_match` (TODO R0/R1)."""

    @abstractmethod
    def begin_segment_round(
        self,
        match: Match,
        segment_id: str,
        *,
        round_no: int,
        deadline_at: datetime,
    ) -> Round:
        """Open a TOURNAMENT segment round (§5 / §7.1)."""

    @abstractmethod
    def save_segment_submission(
        self, match: Match, segment_id: str, player_id: str, hand: Hand
    ) -> None:
        """Store/overwrite a hand for a TOURNAMENT segment round (§7)."""

    @abstractmethod
    def mark_segment_judged(self, match: Match, segment_id: str, *, now: datetime) -> None:
        """Stamp `judged_at` on a TOURNAMENT segment round (§7.1)."""

    @abstractmethod
    def apply_score_deltas(self, match: Match, deltas: list[tuple[str, int]]) -> None:
        """Add score deltas to `match.scores` (BOSS rule, §8)."""

    @abstractmethod
    def set_switched_to_normal_finish(self, match: Match, *, value: bool = True) -> None:
        """Record MINORITY -> NORMAL finish transition (§8)."""

    @abstractmethod
    def set_minority_defer_normal_next_match(self, match: Match, *, value: bool = True) -> None:
        """Record MINORITY NEXT_MATCH timing: switch rule_type to NORMAL after match (§8/§9)."""

    @abstractmethod
    def set_match_state(
        self, match: Match, target: MatchState, *, now: datetime | None = None
    ) -> None:
        """Apply a validated Match.state transition (ARCHITECTURE.md §6).

        Raises `IllegalMatchTransition` if the move is not allowed. `now` (if
        given) stamps `ended_at` when transitioning to MATCH_END.
        """

    @abstractmethod
    def begin_round(self, match: Match, *, round_no: int, deadline_at: datetime) -> Round:
        """Open a fresh round (empty submissions) and bump `current_round_no` (§5)."""

    @abstractmethod
    def save_submission(self, match: Match, player_id: str, hand: Hand) -> None:
        """Store/overwrite a player's hand for the current round (§7)."""

    @abstractmethod
    def mark_round_judged(self, match: Match, *, now: datetime) -> None:
        """Stamp `judged_at` on the current round (double-judge guard, §7.1)."""

    @abstractmethod
    def set_alive(self, match: Match, alive_player_ids: list[str]) -> None:
        """Replace the alive set (after elimination, §7/§8)."""

    @abstractmethod
    def increment_draw_count(self, match: Match) -> int:
        """Count one same-member draw and return the new total (§9 max_draw_rounds)."""

    @abstractmethod
    def finalize_match(self, match: Match, *, winner_ids: list[str], now: datetime) -> None:
        """Record winners and transition the match to MATCH_END (§6)."""

    @abstractmethod
    def touch(self, room: Room) -> None:
        """Update `last_active_at` for idle-sweep accounting (ARCHITECTURE.md §10)."""

    @abstractmethod
    def room_lock(self, room_code: str) -> asyncio.Lock:
        """Return the per-room serialization lock (ARCHITECTURE.md §4/§7.1)."""


class InMemoryGameStateStore(GameStateStore):
    """Single-process, in-memory store (MVP authoritative state)."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get_room(self, room_code: str) -> Room | None:
        return self._rooms.get(room_code.upper())

    def all_rooms(self) -> list[Room]:
        return list(self._rooms.values())

    def create_room(self, host: Player) -> Room:
        code = self._unique_code()
        now = utcnow()
        host.is_host = True
        room = Room(
            room_code=code,
            host_player_id=host.player_id,
            members={host.player_id: host},
            created_at=now,
            last_active_at=now,
        )
        self._rooms[code] = room
        self._locks[code] = asyncio.Lock()
        return room

    def add_player(self, room: Room, player: Player) -> None:
        room.members[player.player_id] = player
        self.touch(room)

    def get_player(self, room: Room, player_id: str) -> Player | None:
        return room.members.get(player_id)

    def get_player_by_token(self, room: Room, token: str) -> Player | None:
        for player in room.members.values():
            if verify_token(player.token, token):
                return player
        return None

    def set_connection_state(
        self, room: Room, player_id: str, state: ConnectionState, *, now: datetime | None = None
    ) -> None:
        player = room.members.get(player_id)
        if player is None:
            return
        when = now if now is not None else utcnow()
        player.connection_state = state
        if state is ConnectionState.DISCONNECTED:
            player.disconnected_at = when
        else:
            player.disconnected_at = None
            player.last_seen_at = when
        self.touch(room)

    def touch_player(self, room: Room, player_id: str, *, now: datetime) -> None:
        player = room.members.get(player_id)
        if player is None:
            return
        player.last_seen_at = now
        self.touch(room)

    def remove_player(self, room: Room, player_id: str) -> None:
        if player_id in room.members:
            del room.members[player_id]
            self.touch(room)

    def set_host(self, room: Room, player_id: str) -> None:
        for member in room.members.values():
            member.is_host = member.player_id == player_id
        room.host_player_id = player_id
        self.touch(room)

    def oldest_connected_human_id(self, room: Room, *, exclude_id: str | None = None) -> str | None:
        candidates = [
            p
            for p in room.members.values()
            if not p.is_cpu
            and p.connection_state is ConnectionState.CONNECTED
            and p.player_id != exclude_id
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda p: p.joined_at).player_id

    def close_room(self, room: Room) -> None:
        room.status = RoomStatus.CLOSED
        self.touch(room)

    def return_to_lobby(self, room: Room) -> list[str]:
        removed: list[str] = []
        for player_id, player in list(room.members.items()):
            if not player.is_cpu and player.connection_state is ConnectionState.DISCONNECTED:
                del room.members[player_id]
                removed.append(player_id)
            else:
                player.is_spectator = False
        room.match = None
        room.status = RoomStatus.WAITING
        self.touch(room)
        return removed

    def set_config(self, room: Room, config: MatchConfig) -> None:
        room.config = config
        self.touch(room)

    def start_match(
        self,
        room: Room,
        *,
        alive_player_ids: list[str],
        config: MatchConfig,
        match_id: str,
        now: datetime,
    ) -> Match:
        match = Match(
            match_id=match_id,
            rule_type=config.rule_type,
            state=MatchState.COLLECTING,
            config=config,
            alive_player_ids=list(alive_player_ids),
            participant_player_ids=list(alive_player_ids),
            scores={},
            # current_round_no stays 0 until the first ROUND_START (Step 9) sets 1.
            current_round_no=0,
            started_at=now,
        )
        room.match = match
        room.status = RoomStatus.IN_GAME
        room.last_active_at = now
        self.init_match_for_rule(match, config)
        return match

    def init_match_for_rule(self, match: Match, config: MatchConfig) -> None:
        """Reset rule-specific fields and apply rule-type defaults (§5 / TODO R0)."""
        match.switched_to_normal_finish = False
        match.minority_defer_normal_next_match = False
        match.tournament_bracket_round = 0
        match.tournament_active_pairs = []
        match.tournament_segment_rounds = {}
        match.tournament_segment_draw_counts = {}
        match.tournament_segment_winners = {}
        match.boss_player_id = None

        if config.rule_type is RuleType.BOSS:
            match.boss_player_id = config.boss_player_id
        elif config.rule_type is RuleType.TOURNAMENT:
            bracket = build_tournament_bracket(match.alive_player_ids)
            match.tournament_active_pairs = [
                TournamentPair(segment_id=pair.segment_id, players=pair.players)
                for pair in bracket.first_round
            ]
            for pair in match.tournament_active_pairs:
                if len(pair.players) == 1:
                    match.tournament_segment_winners[pair.segment_id] = pair.players[0]

    def begin_segment_round(
        self,
        match: Match,
        segment_id: str,
        *,
        round_no: int,
        deadline_at: datetime,
    ) -> Round:
        rnd = Round(round_no=round_no, deadline_at=deadline_at)
        match.tournament_segment_rounds[segment_id] = rnd
        match.current_round_no = round_no
        return rnd

    def save_segment_submission(
        self, match: Match, segment_id: str, player_id: str, hand: Hand
    ) -> None:
        rnd = match.tournament_segment_rounds.get(segment_id)
        if rnd is None:
            return
        rnd.submissions[player_id] = hand

    def mark_segment_judged(self, match: Match, segment_id: str, *, now: datetime) -> None:
        rnd = match.tournament_segment_rounds.get(segment_id)
        if rnd is not None:
            rnd.judged_at = now

    def apply_score_deltas(self, match: Match, deltas: list[tuple[str, int]]) -> None:
        for player_id, delta in deltas:
            match.scores[player_id] = match.scores.get(player_id, 0) + delta

    def set_switched_to_normal_finish(self, match: Match, *, value: bool = True) -> None:
        match.switched_to_normal_finish = value

    def set_minority_defer_normal_next_match(self, match: Match, *, value: bool = True) -> None:
        match.minority_defer_normal_next_match = value

    def set_match_state(
        self, match: Match, target: MatchState, *, now: datetime | None = None
    ) -> None:
        allowed = _MATCH_TRANSITIONS.get(match.state, frozenset())
        if target not in allowed:
            raise IllegalMatchTransition(f"illegal match transition: {match.state} -> {target}")
        match.state = target
        if target is MatchState.MATCH_END and now is not None:
            match.ended_at = now

    def begin_round(self, match: Match, *, round_no: int, deadline_at: datetime) -> Round:
        rnd = Round(round_no=round_no, deadline_at=deadline_at)
        match.current_round = rnd
        match.current_round_no = round_no
        return rnd

    def save_submission(self, match: Match, player_id: str, hand: Hand) -> None:
        if match.current_round is None:
            return
        match.current_round.submissions[player_id] = hand

    def mark_round_judged(self, match: Match, *, now: datetime) -> None:
        if match.current_round is not None:
            match.current_round.judged_at = now

    def set_alive(self, match: Match, alive_player_ids: list[str]) -> None:
        match.alive_player_ids = list(alive_player_ids)

    def increment_draw_count(self, match: Match) -> int:
        match.draw_round_count += 1
        return match.draw_round_count

    def finalize_match(self, match: Match, *, winner_ids: list[str], now: datetime) -> None:
        match.winner_ids = list(winner_ids)
        self.set_match_state(match, MatchState.MATCH_END, now=now)

    def touch(self, room: Room) -> None:
        room.last_active_at = utcnow()

    def room_lock(self, room_code: str) -> asyncio.Lock:
        return self._locks.setdefault(room_code.upper(), asyncio.Lock())

    def _unique_code(self) -> str:
        for _ in range(ROOM_CODE_MAX_GEN_ATTEMPTS):
            code = generate_room_code()
            if code not in self._rooms:
                return code
        raise RoomCodeExhaustedError(
            "Could not generate a unique room code; too many active rooms."
        )
