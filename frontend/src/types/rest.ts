/**
 * REST request/response DTOs (ARCHITECTURE.md §3.1).
 */

import type { RuleType } from '@/types/domain';
import type { ErrorCode } from '@/types/errors';
import type { IsoDateTime } from '@/types/time';
import type { RoomView } from '@/types/domain';

export interface JoinRequest {
  display_name: string;
}

export interface ErrorResponse {
  code: ErrorCode;
  message: string;
}

export interface CreateRoomResponse {
  room_code: string;
  player_id: string;
  player_token: string;
  room: RoomView;
}

export interface JoinRoomResponse {
  player_id: string;
  player_token: string;
  room: RoomView;
}

export interface RoomStateResponse {
  room: RoomView;
}

/** Public server flags (`GET /config`). */
export interface PublicConfigResponse {
  allow_cpu: boolean;
}

/** Participant row in a match history entry (ARCHITECTURE.md §3.1 / §6). */
export interface MatchHistoryPlayerEntry {
  player_id: string;
  display_name: string;
  is_cpu: boolean;
}

/** One finished match in `GET /rooms/{code}/matches` (ARCHITECTURE.md §3.1). */
export interface MatchHistoryEntry {
  match_id: string;
  rule_type: RuleType;
  players: MatchHistoryPlayerEntry[];
  winner_ids: string[];
  scores: Record<string, number>;
  started_at: IsoDateTime;
  ended_at: IsoDateTime;
}

/** `GET /rooms/{code}/matches` success body (ARCHITECTURE.md §3.1). */
export interface MatchHistoryListResponse {
  room_code: string;
  matches: MatchHistoryEntry[];
  has_more: boolean;
}
