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
from app.game.draw_resolution import resolve_after_normal_round
from app.game.engine import RoundOutcome, judge_normal_round
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
    SubmissionUpdatePayload,
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
        await self._start_round(room, None)

    async def submit_hand(
        self, room: Room, player: Player, round_no: int, hand: Hand
    ) -> ErrorCode | None:
        """Accept a hand for the current round; early-finish when all submit (§7).

        Returns an `ErrorCode` to relay to the sender on rejection, else None
        (success is fully handled here: SUBMISSION_UPDATE broadcast and, when the
        whole alive set has submitted, cancelling the timer and judging).
        """
        segment_id: str | None = None
        lock = self._store.room_lock(room.room_code)
        submission_update: dict[str, Any] | None = None
        all_submitted = False
        current_round_no = 0
        async with lock:
            match = room.match
            if match is None or room.status is not RoomStatus.IN_GAME:
                return ErrorCode.INVALID_STATE
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
            submission_update = self._submission_update_msg(match, submitted, segment_id)
            all_submitted = len(submitted) >= len(match.alive_player_ids)
            current_round_no = match.current_round_no

        assert submission_update is not None
        await self._manager.broadcast(room.room_code, submission_update)
        if all_submitted:
            self._cancel_key((room.room_code.upper(), segment_id))
            self._spawn(self._resolve_round(room, segment_id, current_round_no))
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

    async def _cpu_submit_after_delay(
        self,
        room: Room,
        player: Player,
        round_no: int,
        hand: Hand,
        delay: float,
    ) -> None:
        try:
            await self._cpu_delay_sleep(delay)
        except asyncio.CancelledError:
            return
        err = await self.submit_hand(room, player, round_no, hand)
        if err is not None:
            logger.debug(
                "CPU submit ignored for %s in %s: %s",
                player.player_id,
                room.room_code,
                err,
            )

    def _schedule_cpu_submissions(self, room: Room, segment_id: str | None, round_no: int) -> None:
        match = room.match
        if match is None or match.current_round is None:
            return
        limit = float(match.config.round_time_limit_sec)
        for pid in match.alive_player_ids:
            player = self._store.get_player(room, pid)
            if player is None or not player.is_cpu:
                continue
            strategy = player.cpu_strategy or CpuStrategy.RANDOM
            hand = self._pick_hand(strategy)
            delay = compute_submit_delay(limit, uniform=self._uniform)
            self._spawn(self._cpu_submit_after_delay(room, player, round_no, hand, delay))

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
            outcome = judge_normal_round(match.alive_player_ids, rnd.submissions)
            self._store.mark_round_judged(match, now=now)

            config = match.config
            advance_mode = config.round_advance_mode
            result_display_sec = config.result_display_sec

            progression = resolve_after_normal_round(
                outcome, match.alive_player_ids, match.draw_round_count, config
            )
            match.draw_round_count = progression.draw_round_count
            eliminated = list(progression.eliminated_player_ids)
            new_alive = list(progression.alive_player_ids)
            ended = progression.match_ended
            reason = progression.match_end_reason
            winners_final = list(progression.match_winner_ids)

            self._store.set_alive(match, new_alive)
            self._store.set_match_state(match, MatchState.ROUND_RESULT)
            messages.append(self._round_result_msg(rnd, outcome, new_alive, eliminated, segment_id))
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
        self, match: Match, deadline: datetime, now: datetime, segment_id: str | None
    ) -> dict[str, Any]:
        payload = RoundStartPayload(
            round_no=match.current_round_no,
            deadline_at=isoformat_utc(deadline),
            server_now=isoformat_utc(now),
            alive_player_ids=list(match.alive_player_ids),
            segment_id=segment_id,
        )
        return make_envelope(MessageType.ROUND_START, payload.model_dump(mode="json"))

    def _submission_update_msg(
        self, match: Match, submitted_player_ids: list[str], segment_id: str | None
    ) -> dict[str, Any]:
        payload = SubmissionUpdatePayload(
            round_no=match.current_round_no,
            submitted_player_ids=submitted_player_ids,
            expected_count=len(match.alive_player_ids),
            segment_id=segment_id,
        )
        return make_envelope(MessageType.SUBMISSION_UPDATE, payload.model_dump(mode="json"))

    def _round_result_msg(
        self,
        rnd: Round,
        outcome: RoundOutcome,
        alive_player_ids: list[str],
        eliminated_player_ids: list[str],
        segment_id: str | None,
    ) -> dict[str, Any]:
        payload = RoundResultPayload(
            round_no=rnd.round_no,
            hands=dict(rnd.submissions),
            is_draw=outcome.is_draw,
            winner_ids=list(outcome.winner_ids),
            eliminated_player_ids=eliminated_player_ids,
            alive_player_ids=alive_player_ids,
            scores={},  # NORMAL has no scores (§4 scores note)
            segment_id=segment_id,
        )
        return make_envelope(MessageType.ROUND_RESULT, payload.model_dump(mode="json"))

    def _match_end_msg(self, match: Match, reason: MatchEndReason) -> dict[str, Any]:
        payload = MatchEndPayload(
            match_id=match.match_id,
            winner_ids=list(match.winner_ids),
            scores={},
            reason=reason,
        )
        return make_envelope(MessageType.MATCH_END, payload.model_dump(mode="json"))
