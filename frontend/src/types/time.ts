/**
 * UTC time conventions (ARCHITECTURE.md §4).
 *
 * All server timestamps are ISO8601 with millisecond precision and a trailing
 * `Z` (e.g. `2026-06-29T08:00:00.000Z`). Remaining time must be derived from
 * `server_now` and `deadline_at`, never the device clock.
 */

/** UTC ISO8601 string with ms precision and trailing `Z`. */
export type IsoDateTime = string;

const ISO_UTC_MS_Z = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;

export function isIsoDateTime(value: string): value is IsoDateTime {
  return ISO_UTC_MS_Z.test(value);
}

/** Milliseconds from `serverNow` until `deadlineAt` (negative when past). */
export function remainingMs(serverNow: IsoDateTime, deadlineAt: IsoDateTime): number {
  return Date.parse(deadlineAt) - Date.parse(serverNow);
}
