"""Protocol / feel fixed values.

These are NOT placed in `.env` (see ARCHITECTURE.md §1/§4/§6/§10/§11). They are
either protocol invariants (must match the frontend) or feel-related constants.
Heartbeat values in particular must be kept in sync with the frontend constants.
"""

from __future__ import annotations

# --- WebSocket protocol ---------------------------------------------------
# Envelope version. All WS messages use {"type": T, "payload": P, "v": 1}.
WS_PROTOCOL_VERSION = 1

# Max accepted size of a single inbound WS message (bytes). Larger -> dropped.
WS_MAX_MESSAGE_BYTES = 8192

# --- Heartbeat (must match frontend constants) ----------------------------
# Interval at which PING/PONG is exchanged.
HEARTBEAT_INTERVAL_SEC = 25
# If no PONG for ~2 intervals, the player is marked DISCONNECTED.
HEARTBEAT_TIMEOUT_SEC = 60

# --- CPU auto-submit delay (ARCHITECTURE.md §6) ---------------------------
CPU_SUBMIT_DELAY_MIN_SEC = 0.3
CPU_SUBMIT_DELAY_MAX_SEC = 1.5
# Safety margin so the CPU always submits before the deadline.
CPU_SUBMIT_DELAY_EPSILON_SEC = 0.25

# --- Background sweep (ARCHITECTURE.md §10) --------------------------------
# Interval at which all rooms are scanned for idle teardown / ghost pruning.
ROOM_SWEEP_INTERVAL_SEC = 60

# --- Room code (REQUIREMENTS.md §3) ---------------------------------------
# 4-char uppercase alphanumeric, excluding visually ambiguous chars 0 O 1 I L.
ROOM_CODE_LENGTH = 4
ROOM_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
# Regenerate on collision; give up after this many attempts (ARCHITECTURE.md §3.1).
ROOM_CODE_MAX_GEN_ATTEMPTS = 100

# Match history list (`GET /rooms/{code}/matches`, ARCHITECTURE.md §3.1).
MATCH_HISTORY_DEFAULT_LIMIT = 20
MATCH_HISTORY_MAX_LIMIT = 50

# --- Room capacity (REQUIREMENTS.md §3 / ARCHITECTURE.md §4.2) -------------
ROOM_CAPACITY = 20

# --- Display name (ARCHITECTURE.md §3.2) ----------------------------------
DISPLAY_NAME_MIN_LEN = 1
DISPLAY_NAME_MAX_LEN = 20
