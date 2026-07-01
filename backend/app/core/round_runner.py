"""Round progression orchestration (ARCHITECTURE.md §6/§7/§7.1/§8).

This is the side-effectful layer that drives a NORMAL match forward: it opens
rounds, schedules the authoritative deadline timer, collects submissions, judges
(once) and broadcasts the results, then advances or ends the match. The pure
win/loss rule lives in `game/engine.py`; this module wires it to the
`GameStateStore` and `ConnectionManager`.

Concurrency / "judge exactly once" (§7.1):

- Timers and judging are keyed by `(room_code, segment_id)`. NORMAL uses a single
  segment (`segment_id=None`); the key shape leaves room for TOURNAMENT's
  concurrent pairs (Phase 3).
- Every state mutation runs inside the per-room `asyncio.Lock`. Both the
  "everyone submitted" path and the "deadline reached" path call `_resolve_round`,
  which re-checks under the lock that this round is still un-judged and only then
  judges; the late caller is a no-op. Actual WS sends happen outside the lock.

Determinism (.cursor/rules/backend.mdc):

- `now()` and the two sleeps (round deadline, AUTO result display) are injected so
  tests can drive timing without wall-clock dependence.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from app.core.connection_manager import ConnectionManager
from app.core.match_history import MatchHistoryRepository
from app.core.state_store import GameStateStore
from app.game.cpu import compute_submit_delay, pick_random_hand
from app.game.draw_resolution import (
    RoundProgression,
    resolve_after_boss_round,
    resolve_after_minority_round,
    resolve_after_normal_round,
    resolve_after_tournament_pair,
)
from app.game.engine import RoundOutcome, judge_normal_round
from app.game.rules.boss_battle import BossRoundOutcome, judge_boss_round
from app.game.rules.minority import effective_judging_rule, judge_minority_round
from app.game.rules.tournament import (
    TournamentPair as RuleTournamentPair,
)
from app.game.rules.tournament import (
    collect_round_winners,
    judge_tournament_pair,
    next_bracket_round,
    tournament_champion,
)
from app.models import (
    CpuStrategy,
    ErrorCode,
    Hand,
    Match,
    MatchEndPayload,
    MatchEndReason,
    MatchState,
    MessageType,
    Player,
    Room,
    RoomStatus,
    Round,
    RoundAdvanceMode,
    RoundResultPayload,
    RoundStartPayload,
    RuleType,
    SubmissionUpdatePayload,
    TournamentPair,
    make_envelope,
)
from app.utils import isoformat_utc, utcnow

logger = logging.getLogger("rps.round")

SleepFn = Callable[[float], Awaitable[None]]
NowFn = Callable[[], datetime]
UniformFn = Callable[[float, float], float]
PickHandFn = Callable[[CpuStrategy], Hand]

# Timer/judge key: (uppercase room_code, segment_id). NORMAL -> segment_id None.
_SegmentKey = tuple[str, str | None]


async def _real_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


class RoundRunner:
    """Drives ROUND_START -> SUBMIT -> judge -> ROUND_RESULT -> next/MATCH_END."""

    def __init__(
        self,
        store: GameStateStore,
        manager: ConnectionManager,
        match_history: MatchHistoryRepository | None = None,
        *,
        now: NowFn = utcnow,
        deadline_sleep: SleepFn = _real_sleep,
        result_delay_sleep: SleepFn = _real_sleep,
        cpu_delay_sleep: SleepFn = _real_sleep,
        uniform: UniformFn = random.uniform,
        pick_hand: PickHandFn | None = None,
    ) -> None:
        self._store = store
        self._manager = manager
        self._match_history = match_history
        self._now = now
        self._deadline_sleep = deadline_sleep
        self._result_delay_sleep = result_delay_sleep
        self._cpu_delay_sleep = cpu_delay_sleep
        self._uniform = uniform
        self._pick_hand = pick_hand or (lambda strategy: pick_random_hand(strategy=strategy))
        self._timers: dict[_SegmentKey, asyncio.Task[None]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------ API
    async def start_first_round(self, room: Room) -> None:
        """Begin round 1 right after START_GAME created the match (COLLECTING)."""
        match = room.match
        if match is not None and match.rule_type is RuleType.TOURNAMENT:
            await self._start_tournament_stage(room)
            return
        await self._start_round(room, None)

    async def submit_hand(
        self,
        room: Room,
        player: Player,
        round_no: int,
        hand: Hand,
        *,
        segment_id: str | None = None,
    ) -> ErrorCode | None:
        """Accept a hand for the current round; early-finish when all submit (§7).

        Returns an `ErrorCode` to relay to the sender on rejection, else None
        (success is fully handled here: SUBMISSION_UPDATE broadcast and, when the
        whole alive set has submitted, cancelling the timer and judging).
        """
        lock = self._store.room_lock(room.room_code)
        submission_update: dict[str, Any] | None = None
        all_submitted = False
        current_round_no = 0
        resolved_segment_id: str | None = None
        async with lock:
            match = room.match
            if match is None or room.status is not RoomStatus.IN_GAME:
                return ErrorCode.INVALID_STATE
            if match.rule_type is RuleType.TOURNAMENT:
                if segment_id is None:
                    return ErrorCode.INVALID_STATE
                if match.state is not MatchState.COLLECTING:
                    return ErrorCode.INVALID_STATE
                pair = self._pair_for_player(match.tournament_active_pairs, player.player_id)
                if pair is None or pair.segment_id != segment_id or len(pair.players) == 1:
                    return ErrorCode.INVALID_STATE
                if player.is_spectator or player.player_id not in pair.players:
                    return ErrorCode.NOT_ALIVE
                rnd = match.tournament_segment_rounds.get(segment_id)
                if rnd is None or rnd.judged_at is not None:
                    return ErrorCode.INVALID_STATE
                if round_no != rnd.round_no:
                    return ErrorCode.INVALID_STATE
                self._store.save_segment_submission(match, segment_id, player.player_id, hand)
                self._store.touch(room)
                submitted = [pid for pid in pair.players if pid in rnd.submissions]
                resolved_segment_id = segment_id
                submission_update = self._submission_update_msg(
                    match,
                    submitted,
                    segment_id,
                    expected_count=2,
                    round_no=rnd.round_no,
                )
                all_submitted = len(submitted) >= 2
                current_round_no = rnd.round_no
            else:
                if segment_id is not None:
                    return ErrorCode.INVALID_STATE
                resolved_segment_id = None
                if match.state is not MatchState.COLLECTING or match.current_round is None:
                    return ErrorCode.INVALID_STATE
                if player.is_spectator or player.player_id not in match.alive_player_ids:
                    return ErrorCode.NOT_ALIVE
                if round_no != match.current_round_no:
                    return ErrorCode.INVALID_STATE

                self._store.save_submission(match, player.player_id, hand)
                self._store.touch(room)
                rnd = match.current_round
                submitted = [pid for pid in match.alive_player_ids if pid in rnd.submissions]
                submission_update = self._submission_update_msg(
                    match, submitted, resolved_segment_id
                )
                all_submitted = len(submitted) >= len(match.alive_player_ids)
                current_round_no = match.current_round_no

        assert submission_update is not None
        await self._manager.broadcast(room.room_code, submission_update)
        if all_submitted:
            self._cancel_key((room.room_code.upper(), resolved_segment_id))
            self._spawn(self._resolve_round(room, resolved_segment_id, current_round_no))
        return None

    async def next_round(self, room: Room, player: Player) -> ErrorCode | None:
        """Host advances to the next round in MANUAL mode (§6). Returns error or None."""
        segment_id: str | None = None
        lock = self._store.room_lock(room.room_code)
        proceed = False
        async with lock:
            if player.player_id != room.host_player_id:
                return ErrorCode.NOT_HOST
            match = room.match
            if match is None:
                return ErrorCode.INVALID_STATE
            if match.config.round_advance_mode is not RoundAdvanceMode.MANUAL:
                return ErrorCode.INVALID_STATE
            if match.state is not MatchState.ROUND_RESULT:
                return ErrorCode.INVALID_STATE
            proceed = True
        if proceed:
            match = room.match
            if match is not None and match.rule_type is RuleType.TOURNAMENT:
                await self._start_tournament_stage(room)
            else:
                await self._start_round(room, segment_id)
        return None

    async def shutdown(self) -> None:
        """Cancel all timers/advance tasks (lifespan shutdown)."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(BaseException):
                await task
        self._tasks.clear()
        self._timers.clear()

    # -------------------------------------------------------------- internal
    async def _start_round(self, room: Room, segment_id: str | None) -> None:
        lock = self._store.room_lock(room.room_code)
        msg: dict[str, Any] | None = None
        round_no = 0
        seconds = 0.0
        async with lock:
            match = room.match
            if match is None or match.state is MatchState.MATCH_END:
                return
            # Re-rounds arrive in ROUND_RESULT; the first round is already COLLECTING.
            if match.state is MatchState.ROUND_RESULT:
                self._store.set_match_state(match, MatchState.COLLECTING)
            if match.state is not MatchState.COLLECTING:
                return
            round_no = match.current_round_no + 1
            now = self._now()
            deadline = now + timedelta(seconds=match.config.round_time_limit_sec)
            self._store.begin_round(match, round_no=round_no, deadline_at=deadline)
            self._store.touch(room)
            seconds = float(match.config.round_time_limit_sec)
            msg = self._round_start_msg(match, deadline, now, segment_id)

        assert msg is not None
        await self._manager.broadcast(room.room_code, msg)
        self._schedule_deadline(room, segment_id, round_no, seconds)
        self._schedule_cpu_submissions(room, segment_id, round_no)

    async def _start_tournament_stage(self, room: Room) -> None:
        """Open parallel segment rounds for the current bracket stage (§7.1)."""
        lock = self._store.room_lock(room.room_code)
        messages: list[dict[str, Any]] = []
        segments_to_schedule: list[tuple[TournamentPair, int, float]] = []
        async with lock:
            match = room.match
            if match is None or match.state is MatchState.MATCH_END:
                return
            if match.state is MatchState.ROUND_RESULT:
                self._store.set_match_state(match, MatchState.COLLECTING)
            if match.state is not MatchState.COLLECTING:
                return

            stage_round_no = match.current_round_no + 1
            now = self._now()
            deadline = now + timedelta(seconds=match.config.round_time_limit_sec)
            seconds = float(match.config.round_time_limit_sec)

            for pair in match.tournament_active_pairs:
                if len(pair.players) == 1:
                    continue
                self._store.begin_segment_round(
                    match, pair.segment_id, round_no=stage_round_no, deadline_at=deadline
                )
                messages.append(
                    self._round_start_msg(
                        match,
                        deadline,
                        now,
                        pair.segment_id,
                        alive_player_ids=list(pair.players),
                        round_no=stage_round_no,
                    )
                )
                segments_to_schedule.append((pair, stage_round_no, seconds))
            self._store.touch(room)

        for msg in messages:
            await self._manager.broadcast(room.room_code, msg)
        for pair, round_no, seconds in segments_to_schedule:
            self._schedule_deadline(room, pair.segment_id, round_no, seconds)
            self._schedule_cpu_submissions(room, pair.segment_id, round_no)

        if await self._maybe_complete_tournament_stage(room):
            return

    async def _start_tournament_segment_replay(
        self, room: Room, pair: TournamentPair, round_no: int
    ) -> None:
        """Replay one tournament pair after a draw (§7.1)."""
        lock = self._store.room_lock(room.room_code)
        msg: dict[str, Any] | None = None
        seconds = 0.0
        async with lock:
            match = room.match
            if match is None or match.state is MatchState.MATCH_END:
                return
            if match.state is MatchState.ROUND_RESULT:
                self._store.set_match_state(match, MatchState.COLLECTING)
            now = self._now()
            deadline = now + timedelta(seconds=match.config.round_time_limit_sec)
            self._store.begin_segment_round(
                match, pair.segment_id, round_no=round_no, deadline_at=deadline
            )
            self._store.touch(room)
            seconds = float(match.config.round_time_limit_sec)
            msg = self._round_start_msg(
                match,
                deadline,
                now,
                pair.segment_id,
                alive_player_ids=list(pair.players),
                round_no=round_no,
            )

        assert msg is not None
        await self._manager.broadcast(room.room_code, msg)
        self._schedule_deadline(room, pair.segment_id, round_no, seconds)
        self._schedule_cpu_submissions(room, pair.segment_id, round_no)

    async def _resolve_tournament_segment(
        self, room: Room, segment_id: str, expected_round_no: int
    ) -> None:
        lock = self._store.room_lock(room.room_code)
        messages: list[dict[str, Any]] = []
        ended = False
        replay_pair: TournamentPair | None = None
        replay_round_no = 0
        advance_mode = RoundAdvanceMode.AUTO
        result_display_sec = 0
        stage_complete = False
        async with lock:
            match = room.match
            if match is None:
                return
            pair = self._pair_for_segment(match.tournament_active_pairs, segment_id)
            if pair is None or len(pair.players) == 1:
                return
            rnd = match.tournament_segment_rounds.get(segment_id)
            if rnd is None or rnd.judged_at is not None:
                return
            if match.state is not MatchState.COLLECTING:
                return
            if rnd.round_no != expected_round_no:
                return

            now = self._now()
            self._store.set_match_state(match, MatchState.JUDGING)
            player_a, player_b = pair.players[0], pair.players[1]
            draw_count = match.tournament_segment_draw_counts.get(segment_id, 0)
            outcome = judge_tournament_pair(player_a, player_b, rnd.submissions)
            pair_progress = resolve_after_tournament_pair(
                outcome,
                pair.players,
                draw_count,
                match.config.max_draw_rounds,
            )
            self._store.mark_segment_judged(match, segment_id, now=now)
            match.tournament_segment_draw_counts[segment_id] = pair_progress.draw_round_count

            advance_mode = match.config.round_advance_mode
            result_display_sec = match.config.result_display_sec

            if pair_progress.match_ended:
                assert pair_progress.match_end_reason is not None
                self._store.set_match_state(match, MatchState.ROUND_RESULT)
                messages.append(
                    self._round_result_msg(
                        match,
                        rnd,
                        outcome,
                        list(pair.players),
                        list(outcome.eliminated_ids),
                        segment_id,
                    )
                )
                self._store.finalize_match(match, winner_ids=[], now=now)
                messages.append(self._match_end_msg(match, pair_progress.match_end_reason))
                ended = True
            elif pair_progress.replay_pair:
                self._store.set_match_state(match, MatchState.ROUND_RESULT)
                self._store.set_match_state(match, MatchState.COLLECTING)
                messages.append(
                    self._round_result_msg(
                        match,
                        rnd,
                        outcome,
                        list(pair.players),
                        [],
                        segment_id,
                    )
                )
                replay_pair = pair
                replay_round_no = rnd.round_no + 1
            elif pair_progress.pair_complete:
                assert pair_progress.winner_id is not None
                match.tournament_segment_winners[segment_id] = pair_progress.winner_id
                messages.append(
                    self._round_result_msg(
                        match,
                        rnd,
                        outcome,
                        [pair_progress.winner_id],
                        list(outcome.eliminated_ids),
                        segment_id,
                    )
                )
                stage_complete = self._tournament_stage_complete(match)
                if stage_complete:
                    self._store.set_match_state(match, MatchState.ROUND_RESULT)
                else:
                    self._store.set_match_state(match, MatchState.ROUND_RESULT)
                    self._store.set_match_state(match, MatchState.COLLECTING)
            self._store.touch(room)

        for msg in messages:
            await self._manager.broadcast(room.room_code, msg)

        if ended:
            self._cancel_all_room_timers(room.room_code)
            await self._persist_match_history(room)
            return
        if replay_pair is not None:
            await self._start_tournament_segment_replay(room, replay_pair, replay_round_no)
            return
        if stage_complete:
            await self._after_tournament_stage(room, advance_mode, result_display_sec)

    async def _maybe_complete_tournament_stage(self, room: Room) -> bool:
        """If only byes remain unresolved, finish the stage immediately."""
        lock = self._store.room_lock(room.room_code)
        complete = False
        async with lock:
            match = room.match
            if match is None:
                return False
            complete = self._tournament_stage_complete(match)
            if complete:
                self._store.set_match_state(match, MatchState.ROUND_RESULT)
        if complete:
            match = room.match
            assert match is not None
            await self._after_tournament_stage(
                room, match.config.round_advance_mode, match.config.result_display_sec
            )
        return complete

    async def _after_tournament_stage(
        self,
        room: Room,
        advance_mode: RoundAdvanceMode,
        result_display_sec: int,
    ) -> None:
        lock = self._store.room_lock(room.room_code)
        messages: list[dict[str, Any]] = []
        ended = False
        async with lock:
            match = room.match
            if match is None or not self._tournament_stage_complete(match):
                return
            pairs = list(match.tournament_active_pairs)
            segment_winners = dict(match.tournament_segment_winners)
            match.tournament_segment_winners = {}
            outcomes = {
                seg_id: RoundOutcome(
                    is_draw=False,
                    winner_ids=(winner_id,),
                    eliminated_ids=(),
                )
                for seg_id, winner_id in segment_winners.items()
            }
            rule_pairs = [
                RuleTournamentPair(segment_id=p.segment_id, players=p.players) for p in pairs
            ]
            winners = list(collect_round_winners(rule_pairs, outcomes))
            champion = tournament_champion(winners)
            now = self._now()
            self._store.set_alive(match, winners)
            if champion is not None:
                self._store.finalize_match(match, winner_ids=[champion], now=now)
                messages.append(self._match_end_msg(match, MatchEndReason.DECIDED))
                ended = True
            else:
                next_round = match.tournament_bracket_round + 1
                next_pairs = next_bracket_round(winners, next_round)
                assert next_pairs is not None
                match.tournament_bracket_round = next_round
                match.tournament_active_pairs = [
                    TournamentPair(segment_id=p.segment_id, players=p.players) for p in next_pairs
                ]
                match.tournament_segment_rounds = {}
                match.tournament_segment_draw_counts = {}
                match.tournament_segment_winners = {}
                for pair in match.tournament_active_pairs:
                    if len(pair.players) == 1:
                        match.tournament_segment_winners[pair.segment_id] = pair.players[0]
            self._store.touch(room)

        for msg in messages:
            await self._manager.broadcast(room.room_code, msg)
        if ended:
            self._cancel_all_room_timers(room.room_code)
            await self._persist_match_history(room)
            return
        if advance_mode is RoundAdvanceMode.AUTO:
            await self._result_delay_sleep(result_display_sec)
            await self._start_tournament_stage(room)

    def _tournament_stage_complete(self, match: Match) -> bool:
        for pair in match.tournament_active_pairs:
            if pair.segment_id not in match.tournament_segment_winners:
                return False
        return True

    @staticmethod
    def _pair_for_player(pairs: list[TournamentPair], player_id: str) -> TournamentPair | None:
        for pair in pairs:
            if player_id in pair.players:
                return pair
        return None

    @staticmethod
    def _pair_for_segment(pairs: list[TournamentPair], segment_id: str) -> TournamentPair | None:
        for pair in pairs:
            if pair.segment_id == segment_id:
                return pair
        return None

    def _cancel_all_room_timers(self, room_code: str) -> None:
        prefix = room_code.upper()
        for key in list(self._timers):
            if key[0] == prefix:
                self._cancel_key(key)

    async def _cpu_submit_after_delay(
        self,
        room: Room,
        player: Player,
        round_no: int,
        hand: Hand,
        delay: float,
        *,
        segment_id: str | None = None,
    ) -> None:
        try:
            await self._cpu_delay_sleep(delay)
        except asyncio.CancelledError:
            return
        err = await self.submit_hand(room, player, round_no, hand, segment_id=segment_id)
        if err is not None:
            logger.debug(
                "CPU submit ignored for %s in %s: %s",
                player.player_id,
                room.room_code,
                err,
            )

    def _schedule_cpu_submissions(self, room: Room, segment_id: str | None, round_no: int) -> None:
        match = room.match
        if match is None:
            return
        if match.rule_type is RuleType.TOURNAMENT:
            if segment_id is None:
                return
            pair = self._pair_for_segment(match.tournament_active_pairs, segment_id)
            if pair is None or len(pair.players) == 1:
                return
            if match.tournament_segment_rounds.get(segment_id) is None:
                return
            player_ids = list(pair.players)
        else:
            if match.current_round is None:
                return
            player_ids = list(match.alive_player_ids)
        limit = float(match.config.round_time_limit_sec)
        for pid in player_ids:
            player = self._store.get_player(room, pid)
            if player is None or not player.is_cpu:
                continue
            strategy = player.cpu_strategy or CpuStrategy.RANDOM
            hand = self._pick_hand(strategy)
            delay = compute_submit_delay(limit, uniform=self._uniform)
            self._spawn(
                self._cpu_submit_after_delay(
                    room, player, round_no, hand, delay, segment_id=segment_id
                )
            )

    async def _deadline_timer(
        self, room: Room, segment_id: str | None, round_no: int, seconds: float
    ) -> None:
        try:
            await self._deadline_sleep(seconds)
        except asyncio.CancelledError:
            return
        await self._resolve_round(room, segment_id, round_no)

    async def _resolve_round(
        self, room: Room, segment_id: str | None, expected_round_no: int
    ) -> None:
        match = room.match
        if match is not None and match.rule_type is RuleType.TOURNAMENT:
            if segment_id is None:
                return
            await self._resolve_tournament_segment(room, segment_id, expected_round_no)
            return
        await self._resolve_standard_round(room, segment_id, expected_round_no)

    async def _resolve_standard_round(
        self, room: Room, segment_id: str | None, expected_round_no: int
    ) -> None:
        lock = self._store.room_lock(room.room_code)
        messages: list[dict[str, Any]] = []
        ended = False
        advance_mode = RoundAdvanceMode.AUTO
        result_display_sec = 0
        async with lock:
            match = room.match
            if match is None or match.current_round is None:
                return
            rnd = match.current_round
            # Judge exactly once (§7.1): late caller after a finished judge is a no-op.
            if rnd.judged_at is not None or match.state is not MatchState.COLLECTING:
                return
            if match.current_round_no != expected_round_no:
                return  # stale timer for an older round

            now = self._now()
            self._store.set_match_state(match, MatchState.JUDGING)
            outcome, progression = self._judge_and_progress(match, rnd)
            self._store.mark_round_judged(match, now=now)

            config = match.config
            advance_mode = config.round_advance_mode
            result_display_sec = config.result_display_sec

            self._apply_progression_flags(match, progression)
            if progression.score_deltas:
                self._store.apply_score_deltas(match, list(progression.score_deltas))
            match.draw_round_count = progression.draw_round_count
            eliminated = list(progression.eliminated_player_ids)
            new_alive = list(progression.alive_player_ids)
            ended = progression.match_ended
            reason = progression.match_end_reason
            winners_final = list(progression.match_winner_ids)

            self._store.set_alive(match, new_alive)
            self._store.set_match_state(match, MatchState.ROUND_RESULT)
            messages.append(
                self._round_result_msg(match, rnd, outcome, new_alive, eliminated, segment_id)
            )
            if ended:
                assert reason is not None
                self._store.finalize_match(match, winner_ids=winners_final, now=now)
                messages.append(self._match_end_msg(match, reason))
            self._store.touch(room)

        for msg in messages:
            await self._manager.broadcast(room.room_code, msg)

        if ended:
            self._cancel_key((room.room_code.upper(), segment_id))
            await self._persist_match_history(room)
            return
        if advance_mode is RoundAdvanceMode.AUTO:
            await self._result_delay_sleep(result_display_sec)
            await self._start_round(room, segment_id)
        # MANUAL: wait for the host's NEXT_ROUND (handled in `next_round`).

    def _judging_rule(self, match: Match) -> RuleType:
        """Rule used to judge the current round (§8)."""
        if match.rule_type is RuleType.MINORITY:
            return effective_judging_rule(
                match.rule_type, switched_to_normal_finish=match.switched_to_normal_finish
            )
        if match.rule_type is RuleType.BOSS:
            return RuleType.BOSS
        return RuleType.NORMAL

    def _judge_and_progress(
        self, match: Match, rnd: Round
    ) -> tuple[RoundOutcome, RoundProgression]:
        alive = match.alive_player_ids
        subs = rnd.submissions
        config = match.config
        rule = self._judging_rule(match)
        if rule is RuleType.MINORITY:
            outcome = judge_minority_round(alive, subs)
            progression = resolve_after_minority_round(
                outcome,
                alive,
                match.draw_round_count,
                config,
                switched_to_normal_finish=match.switched_to_normal_finish,
            )
        elif rule is RuleType.BOSS:
            boss_id = match.boss_player_id
            if boss_id is None:
                boss_outcome = BossRoundOutcome(is_draw=True)
            else:
                boss_hand = subs.get(boss_id)
                if boss_hand is None:
                    boss_outcome = BossRoundOutcome(is_draw=True)
                else:
                    boss_outcome = judge_boss_round(alive, boss_id, boss_hand, subs)
            progression = resolve_after_boss_round(
                boss_outcome,
                alive,
                boss_id or "",
                match.draw_round_count,
                config.max_draw_rounds,
            )
            outcome = RoundOutcome(is_draw=boss_outcome.is_draw, winner_ids=boss_outcome.winner_ids)
        else:
            outcome = judge_normal_round(alive, subs)
            progression = resolve_after_normal_round(outcome, alive, match.draw_round_count, config)
        return outcome, progression

    def _public_alive_player_ids(self, match: Match, alive_player_ids: list[str]) -> list[str]:
        """Alive competitors for broadcast (§8: BOSS excludes the boss from alive lists)."""
        boss_id = match.boss_player_id
        if match.rule_type is RuleType.BOSS and boss_id is not None:
            return [pid for pid in alive_player_ids if pid != boss_id]
        return list(alive_player_ids)

    def _apply_progression_flags(self, match: Match, progression: RoundProgression) -> None:
        if progression.switched_to_normal_finish and not match.switched_to_normal_finish:
            self._store.set_switched_to_normal_finish(match)
        if progression.minority_defer_normal_next_match:
            self._store.set_minority_defer_normal_next_match(match)

    # ------------------------------------------------------------ scheduling
    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _schedule_deadline(
        self, room: Room, segment_id: str | None, round_no: int, seconds: float
    ) -> None:
        key = (room.room_code.upper(), segment_id)
        self._cancel_key(key)
        task = asyncio.ensure_future(self._deadline_timer(room, segment_id, round_no, seconds))
        self._timers[key] = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        def _clear(done: asyncio.Task[None]) -> None:
            if self._timers.get(key) is done:
                self._timers.pop(key, None)

        task.add_done_callback(_clear)

    def _cancel_key(self, key: _SegmentKey) -> None:
        task = self._timers.pop(key, None)
        if task is not None:
            task.cancel()

    async def _persist_match_history(self, room: Room) -> None:
        """Write finalized match to MongoDB; failures are logged, not propagated (§6)."""
        if self._match_history is None:
            return
        match = room.match
        if match is None or match.state is not MatchState.MATCH_END:
            return
        try:
            await self._match_history.save_finished_match(room, match)
        except Exception:
            logger.exception(
                "Match history persist failed for room=%s match_id=%s.",
                room.room_code,
                match.match_id,
            )

    # --------------------------------------------------------------- messages
    def _round_start_msg(
        self,
        match: Match,
        deadline: datetime,
        now: datetime,
        segment_id: str | None,
        *,
        alive_player_ids: list[str] | None = None,
        round_no: int | None = None,
    ) -> dict[str, Any]:
        payload = RoundStartPayload(
            round_no=round_no if round_no is not None else match.current_round_no,
            deadline_at=isoformat_utc(deadline),
            server_now=isoformat_utc(now),
            alive_player_ids=alive_player_ids or list(match.alive_player_ids),
            segment_id=segment_id,
        )
        return make_envelope(MessageType.ROUND_START, payload.model_dump(mode="json"))

    def _submission_update_msg(
        self,
        match: Match,
        submitted_player_ids: list[str],
        segment_id: str | None,
        *,
        expected_count: int | None = None,
        round_no: int | None = None,
    ) -> dict[str, Any]:
        payload = SubmissionUpdatePayload(
            round_no=round_no if round_no is not None else match.current_round_no,
            submitted_player_ids=submitted_player_ids,
            expected_count=expected_count
            if expected_count is not None
            else len(match.alive_player_ids),
            segment_id=segment_id,
        )
        return make_envelope(MessageType.SUBMISSION_UPDATE, payload.model_dump(mode="json"))

    def _round_result_msg(
        self,
        match: Match,
        rnd: Round,
        outcome: RoundOutcome,
        alive_player_ids: list[str],
        eliminated_player_ids: list[str],
        segment_id: str | None,
    ) -> dict[str, Any]:
        scores = dict(match.scores) if match.rule_type is RuleType.BOSS else {}
        payload = RoundResultPayload(
            round_no=rnd.round_no,
            hands=dict(rnd.submissions),
            is_draw=outcome.is_draw,
            winner_ids=list(outcome.winner_ids),
            eliminated_player_ids=eliminated_player_ids,
            alive_player_ids=self._public_alive_player_ids(match, alive_player_ids),
            scores=scores,
            segment_id=segment_id,
        )
        return make_envelope(MessageType.ROUND_RESULT, payload.model_dump(mode="json"))

    def _match_end_msg(self, match: Match, reason: MatchEndReason) -> dict[str, Any]:
        scores = dict(match.scores) if match.rule_type is RuleType.BOSS else {}
        payload = MatchEndPayload(
            match_id=match.match_id,
            winner_ids=list(match.winner_ids),
            scores=scores,
            reason=reason,
        )
        return make_envelope(MessageType.MATCH_END, payload.model_dump(mode="json"))
