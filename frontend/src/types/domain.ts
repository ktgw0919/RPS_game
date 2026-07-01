/**
 * Domain enums and view DTOs (ARCHITECTURE.md §4 / §5 / §9).
 *
 * Mirrors `backend/app/models.py`. View DTOs never include `player_token`.
 */

// --- Enums / value types (string literal unions match Python StrEnum) -------
export type Hand = 'ROCK' | 'SCISSORS' | 'PAPER';
export type CpuStrategy = 'RANDOM';
export type RuleType = 'NORMAL' | 'MINORITY' | 'BOSS' | 'TOURNAMENT';
export type NormalEndMode = 'ELIMINATION' | 'SINGLE_ROUND';
export type RoundAdvanceMode = 'AUTO' | 'MANUAL';
export type MinorityFinishTiming = 'IMMEDIATE' | 'NEXT_MATCH';
export type RoomStatus = 'WAITING' | 'IN_GAME' | 'CLOSED';
export type MatchState = 'COLLECTING' | 'JUDGING' | 'ROUND_RESULT' | 'MATCH_END';
export type MatchEndReason = 'DECIDED' | 'DRAW_MAX_ROUNDS';
export type ConnectionState = 'CONNECTED' | 'DISCONNECTED';

// --- Host settings (ARCHITECTURE.md §9; ranges/defaults are authoritative) --
export interface MatchConfig {
  rule_type: RuleType;
  normal_end_mode: NormalEndMode;
  round_time_limit_sec: number;
  round_advance_mode: RoundAdvanceMode;
  result_display_sec: number;
  max_draw_rounds: number;
  minority_finish_threshold: number;
  minority_finish_timing: MinorityFinishTiming;
  boss_player_id: string | null;
}

/** Partial config change for `UPDATE_SETTINGS` (only provided fields apply). */
export type MatchConfigUpdate = Partial<MatchConfig>;

/** Server defaults for `MatchConfig` (ARCHITECTURE.md §9). */
export const DEFAULT_MATCH_CONFIG: MatchConfig = {
  rule_type: 'NORMAL',
  normal_end_mode: 'ELIMINATION',
  round_time_limit_sec: 10,
  round_advance_mode: 'AUTO',
  result_display_sec: 3,
  max_draw_rounds: 5,
  minority_finish_threshold: 2,
  minority_finish_timing: 'IMMEDIATE',
  boss_player_id: null,
};

// --- View DTOs (ARCHITECTURE.md §4; never include the token) ----------------
export interface PlayerView {
  player_id: string;
  display_name: string;
  is_host: boolean;
  connection_state: ConnectionState;
  is_spectator: boolean;
  is_cpu: boolean;
}

export interface RoomView {
  room_code: string;
  status: RoomStatus;
  host_player_id: string | null;
  member_count: number;
  capacity: number;
  config: MatchConfig;
}

export interface MatchView {
  match_id: string;
  rule_type: RuleType;
  state: MatchState;
  current_round_no: number;
  alive_player_ids: string[];
  scores: Record<string, number>;
  deadline_at: string | null;
  my_submitted: boolean;
  boss_player_id?: string | null;
  segment_id?: string | null;
}
