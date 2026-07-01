/**
 * Lightweight REST client (ARCHITECTURE.md §3.1).
 *
 * Game state uses WebSocket; match history reads use SWR via `useMatchHistory`.
 */

import { MATCH_HISTORY_DEFAULT_LIMIT } from '@/lib/constants';
import {
  isErrorCode,
  type CreateRoomResponse,
  type ErrorCode,
  type ErrorResponse,
  type JoinRoomResponse,
  type MatchHistoryListResponse,
  type PublicConfigResponse,
  type RoomStateResponse,
} from '@/types';

export class ApiRequestError extends Error {
  readonly code: ErrorCode;
  readonly status: number;

  constructor(body: ErrorResponse, status: number) {
    super(body.message);
    this.name = 'ApiRequestError';
    this.code = body.code;
    this.status = status;
  }
}

async function parseError(response: Response): Promise<ApiRequestError> {
  try {
    const body = (await response.json()) as ErrorResponse;
    if (isErrorCode(body.code) && typeof body.message === 'string') {
      return new ApiRequestError(body, response.status);
    }
  } catch {
    // fall through
  }
  return new ApiRequestError(
    { code: 'INVALID_STATE', message: response.statusText || 'Request failed.' },
    response.status,
  );
}

/** JSON `fetch` wrapper with shared error handling. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type') && init?.body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

export function createRoom(displayName: string): Promise<CreateRoomResponse> {
  return apiFetch<CreateRoomResponse>('/rooms', {
    method: 'POST',
    body: JSON.stringify({ display_name: displayName }),
  });
}

export function joinRoom(roomCode: string, displayName: string): Promise<JoinRoomResponse> {
  return apiFetch<JoinRoomResponse>(`/rooms/${encodeURIComponent(roomCode)}/players`, {
    method: 'POST',
    body: JSON.stringify({ display_name: displayName }),
  });
}

export function getRoom(roomCode: string): Promise<RoomStateResponse> {
  return apiFetch<RoomStateResponse>(`/rooms/${encodeURIComponent(roomCode)}`);
}

export function getPublicConfig(): Promise<PublicConfigResponse> {
  return apiFetch<PublicConfigResponse>('/config');
}

export function getMatchHistory(
  roomCode: string,
  limit: number = MATCH_HISTORY_DEFAULT_LIMIT,
): Promise<MatchHistoryListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return apiFetch<MatchHistoryListResponse>(
    `/rooms/${encodeURIComponent(roomCode)}/matches?${params}`,
  );
}
