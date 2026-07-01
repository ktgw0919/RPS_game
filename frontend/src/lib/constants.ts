/**
 * Protocol constants shared with the backend (`backend/app/core/constants.py`).
 *
 * These MUST be kept in sync with the backend values in the same change
 * (see .cursor/rules/00-project.mdc and ARCHITECTURE.md §1/§4). The heartbeat
 * interval in particular requires front/back agreement.
 */

// WebSocket envelope version: { type, payload, v }
export const WS_PROTOCOL_VERSION = 1;

// Heartbeat (must match backend HEARTBEAT_INTERVAL_SEC / HEARTBEAT_TIMEOUT_SEC).
export const HEARTBEAT_INTERVAL_SEC = 25;
export const HEARTBEAT_TIMEOUT_SEC = 60;

// Room capacity (REQUIREMENTS.md §3 / ARCHITECTURE.md §4.2).
export const ROOM_CAPACITY = 20;

// Display name constraints (ARCHITECTURE.md §3.2). Server-side validation is
// authoritative; this is UX assistance only.
export const DISPLAY_NAME_MIN_LEN = 1;
export const DISPLAY_NAME_MAX_LEN = 20;

// Match history pagination (`backend/app/core/constants.py`).
export const MATCH_HISTORY_DEFAULT_LIMIT = 20;
export const MATCH_HISTORY_MAX_LIMIT = 50;
