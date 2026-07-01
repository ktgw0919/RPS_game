/**
 * Shared error codes (ARCHITECTURE.md §4.1).
 *
 * Kept in sync with `backend/app/models.py` `ErrorCode`. REST and WS both use
 * `{ code, message }` with these codes.
 */

/** All supported `ErrorCode` values (order matches backend `ErrorCode` enum). */
export const ERROR_CODES = [
  'ROOM_NOT_FOUND',
  'ROOM_FULL',
  'ROOM_CLOSED',
  'INVALID_TOKEN',
  'SESSION_REPLACED',
  'DISPLAY_NAME_INVALID',
  'NOT_HOST',
  'NOT_ALIVE',
  'INVALID_STATE',
  'INVALID_PAYLOAD',
  'START_CONDITION_UNMET',
  'CPU_NOT_ALLOWED',
] as const;

export type ErrorCode = (typeof ERROR_CODES)[number];

export function isErrorCode(value: string): value is ErrorCode {
  return (ERROR_CODES as readonly string[]).includes(value);
}

/** WS `ERROR` codes that close the socket (ARCHITECTURE.md §4.1). */
export const FATAL_WS_ERROR_CODES: ReadonlySet<ErrorCode> = new Set([
  'INVALID_TOKEN',
  'SESSION_REPLACED',
  'ROOM_NOT_FOUND',
  'ROOM_CLOSED',
]);

export interface ErrorPayload {
  code: ErrorCode;
  message: string;
}
