/**
 * REST request/response DTOs (ARCHITECTURE.md §3.1).
 */

import type { ErrorCode } from '@/types/errors';
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
