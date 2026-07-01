/**
 * Shared WebSocket / domain types (ARCHITECTURE.md §4).
 *
 * These mirror the backend Pydantic v2 models in `backend/app/models.py` and the
 * envelope form `{ type, payload, v }`. Any change to a WS payload / view DTO /
 * `ErrorCode` / `MatchConfig` must update both sides in the same change
 * (.cursor/rules/frontend.mdc / backend.mdc).
 */

export type {
  ConnectionState,
  CpuStrategy,
  Hand,
  MatchConfig,
  MatchConfigUpdate,
  MatchEndReason,
  MatchState,
  MatchView,
  MinorityFinishTiming,
  NormalEndMode,
  PlayerView,
  RoomStatus,
  RoomView,
  RoundAdvanceMode,
  RuleType,
} from '@/types/domain';
export { DEFAULT_MATCH_CONFIG } from '@/types/domain';

export type { ErrorCode, ErrorPayload } from '@/types/errors';
export { ERROR_CODES, FATAL_WS_ERROR_CODES, isErrorCode } from '@/types/errors';

export type {
  AddCpuPayload,
  ClientEnvelope,
  ClientMessageType,
  ClientPayloadMap,
  EmptyPayload,
  Envelope,
  HostChangedPayload,
  JoinPayload,
  LeavePayload,
  LobbyUpdatePayload,
  MatchEndPayload,
  MessageType,
  NextRoundPayload,
  PlayerJoinedPayload,
  PlayerLeftPayload,
  PongPayload,
  RemoveCpuPayload,
  ReturnToLobbyPayload,
  RoundResultPayload,
  RoundStartPayload,
  ServerEnvelope,
  ServerMessageType,
  ServerPayloadMap,
  SettingsUpdatePayload,
  StartGamePayload,
  StateSyncPayload,
  SubmissionUpdatePayload,
  SubmitHandPayload,
  UpdateSettingsPayload,
  WsConnectionStatus,
  WsProtocolVersion,
} from '@/types/messages';
export {
  isClientMessageType,
  isEnvelope,
  isServerEnvelope,
  isServerMessageType,
  makeClientEnvelope,
} from '@/types/messages';

export type {
  CreateRoomResponse,
  ErrorResponse,
  JoinRequest,
  JoinRoomResponse,
  MatchHistoryEntry,
  MatchHistoryListResponse,
  MatchHistoryPlayerEntry,
  PublicConfigResponse,
  RoomStateResponse,
} from '@/types/rest';

export type { IsoDateTime } from '@/types/time';
export { isIsoDateTime, remainingMs } from '@/types/time';
