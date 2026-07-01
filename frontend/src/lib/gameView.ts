import type { MatchConfig, MatchView, RoundStartPayload } from '@/types';

/**
 * Apply ROUND_START to local match state.
 *
 * After START_GAME the server broadcasts LOBBY_UPDATE (roster only) then
 * ROUND_START. Clients that have not yet received a match snapshot bootstrap
 * from config + ROUND_START (ARCHITECTURE.md §4).
 */
export function matchAfterRoundStart(
  match: MatchView | null,
  config: MatchConfig | null,
  payload: RoundStartPayload,
): MatchView | null {
  if (match) {
    return {
      ...match,
      state: 'COLLECTING',
      current_round_no: payload.round_no,
      deadline_at: payload.deadline_at,
      alive_player_ids: payload.alive_player_ids,
      my_submitted: false,
      segment_id: payload.segment_id ?? match.segment_id ?? null,
    };
  }
  if (!config) return null;
  return {
    match_id: '',
    rule_type: config.rule_type,
    state: 'COLLECTING',
    current_round_no: payload.round_no,
    alive_player_ids: payload.alive_player_ids,
    scores: {},
    deadline_at: payload.deadline_at,
    my_submitted: false,
    boss_player_id: config.boss_player_id,
    segment_id: payload.segment_id ?? null,
  };
}

/** Rebuild round timing from a STATE_SYNC snapshot (reconnect during COLLECTING). */
export function deriveRoundTiming(
  match: MatchView | null,
  serverNow: string | null,
): Pick<
  RoundStartPayload,
  'round_no' | 'deadline_at' | 'server_now' | 'alive_player_ids' | 'segment_id'
> | null {
  if (!match || match.state !== 'COLLECTING' || !match.deadline_at || !serverNow) {
    return null;
  }
  return {
    round_no: match.current_round_no,
    deadline_at: match.deadline_at,
    server_now: serverNow,
    alive_player_ids: match.alive_player_ids,
    segment_id: match.segment_id ?? null,
  };
}
