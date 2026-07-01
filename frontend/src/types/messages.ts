/**
 * WebSocket protocol types (ARCHITECTURE.md §4).
 *
 * Envelope form `{ type, payload, v }` with discriminated unions for inbound
 * parsing and type-safe `send()`.
 */

import { WS_PROTOCOL_VERSION } from '@/lib/constants';
import type {
  CpuStrategy,
  Hand,
  MatchConfig,
  MatchConfigUpdate,
  MatchEndReason,
  MatchView,
  PlayerView,
  RoomView,
} from '@/types/domain';
import type { ErrorPayload } from '@/types/errors';
import type { IsoDateTime } from '@/types/time';

// --- Message type unions ----------------------------------------------------
export type ClientMessageType =
  | 'JOIN'
  | 'PING'
  | 'UPDATE_SETTINGS'
  | 'START_GAME'
  | 'SUBMIT_HAND'
  | 'NEXT_ROUND'
  | 'RETURN_TO_LOBBY'
  | 'LEAVE'
  | 'ADD_CPU'
  | 'REMOVE_CPU';

export type ServerMessageType =
  | 'STATE_SYNC'
  | 'LOBBY_UPDATE'
  | 'SETTINGS_UPDATE'
  | 'ROUND_START'
  | 'SUBMISSION_UPDATE'
  | 'ROUND_RESULT'
  | 'MATCH_END'
  | 'PLAYER_JOINED'
  | 'PLAYER_LEFT'
  | 'HOST_CHANGED'
  | 'PONG'
  | 'ERROR';

export type MessageType = ClientMessageType | ServerMessageType;

/** WebSocket transport status (client-side; not a server domain field). */
export type WsConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'replaced';

// --- Payloads ----------------------------------------------------------------
/** Payload for messages that carry no data (e.g. `PING` / `PONG` / `START_GAME`). */
export type EmptyPayload = Record<string, never>;

export interface JoinPayload {
  token: string;
}

export interface StateSyncPayload {
  room: RoomView;
  members: PlayerView[];
  you: PlayerView;
  match: MatchView | null;
  server_now: IsoDateTime;
}

export interface LobbyUpdatePayload {
  members: PlayerView[];
  host_player_id: string | null;
  config: MatchConfig;
}

export interface SettingsUpdatePayload {
  config: MatchConfig;
}

export interface UpdateSettingsPayload {
  config: MatchConfigUpdate;
}

export type StartGamePayload = EmptyPayload;

/** `segment_id` selects a TOURNAMENT pair; NORMAL omits it / sends null. */
export interface SubmitHandPayload {
  round_no: number;
  hand: Hand;
  segment_id?: string | null;
}

export type NextRoundPayload = EmptyPayload;

export interface RoundStartPayload {
  round_no: number;
  deadline_at: IsoDateTime;
  server_now: IsoDateTime;
  alive_player_ids: string[];
  segment_id?: string | null;
}

export interface SubmissionUpdatePayload {
  round_no: number;
  submitted_player_ids: string[];
  expected_count: number;
  segment_id?: string | null;
}

export interface RoundResultPayload {
  round_no: number;
  hands: Record<string, Hand>;
  is_draw: boolean;
  winner_ids: string[];
  eliminated_player_ids: string[];
  alive_player_ids: string[];
  scores: Record<string, number>;
  segment_id?: string | null;
}

export interface MatchEndPayload {
  match_id: string;
  winner_ids: string[];
  scores: Record<string, number>;
  reason: MatchEndReason;
}

export type LeavePayload = EmptyPayload;
export type ReturnToLobbyPayload = EmptyPayload;
export type PongPayload = EmptyPayload;

export interface AddCpuPayload {
  count?: number;
  strategy?: CpuStrategy;
}

export interface RemoveCpuPayload {
  player_id?: string | null;
}

/** UX-only notice; the accompanying `LOBBY_UPDATE` is the roster authority (§4). */
export interface PlayerJoinedPayload {
  player: PlayerView;
}

/** UX-only notice; the accompanying `LOBBY_UPDATE` is the roster authority (§4). */
export interface PlayerLeftPayload {
  player_id: string;
}

/** UX-only notice; host authority is `LOBBY_UPDATE` / `STATE_SYNC` (§4). */
export interface HostChangedPayload {
  host_player_id: string;
}

// --- Payload maps (type-safe send / dispatch) -------------------------------
export interface ClientPayloadMap {
  JOIN: JoinPayload;
  PING: EmptyPayload;
  UPDATE_SETTINGS: UpdateSettingsPayload;
  START_GAME: StartGamePayload;
  SUBMIT_HAND: SubmitHandPayload;
  NEXT_ROUND: NextRoundPayload;
  RETURN_TO_LOBBY: ReturnToLobbyPayload;
  LEAVE: LeavePayload;
  ADD_CPU: AddCpuPayload;
  REMOVE_CPU: RemoveCpuPayload;
}

export interface ServerPayloadMap {
  STATE_SYNC: StateSyncPayload;
  LOBBY_UPDATE: LobbyUpdatePayload;
  SETTINGS_UPDATE: SettingsUpdatePayload;
  ROUND_START: RoundStartPayload;
  SUBMISSION_UPDATE: SubmissionUpdatePayload;
  ROUND_RESULT: RoundResultPayload;
  MATCH_END: MatchEndPayload;
  PLAYER_JOINED: PlayerJoinedPayload;
  PLAYER_LEFT: PlayerLeftPayload;
  HOST_CHANGED: HostChangedPayload;
  PONG: PongPayload;
  ERROR: ErrorPayload;
}

// --- Envelope (discriminated unions) ----------------------------------------
export type WsProtocolVersion = typeof WS_PROTOCOL_VERSION;

export interface Envelope<P = unknown> {
  type: MessageType;
  payload: P;
  v: WsProtocolVersion;
}

export type ClientEnvelope = {
  [K in ClientMessageType]: { type: K; payload: ClientPayloadMap[K]; v: WsProtocolVersion };
}[ClientMessageType];

export type ServerEnvelope = {
  [K in ServerMessageType]: { type: K; payload: ServerPayloadMap[K]; v: WsProtocolVersion };
}[ServerMessageType];

export function isEnvelope(value: unknown): value is Envelope {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return typeof record.type === 'string' && typeof record.v === 'number' && 'payload' in record;
}

export function isServerEnvelope(value: unknown): value is ServerEnvelope {
  return isEnvelope(value) && value.v === WS_PROTOCOL_VERSION;
}

export function isClientMessageType(type: string): type is ClientMessageType {
  return (
    type === 'JOIN' ||
    type === 'PING' ||
    type === 'UPDATE_SETTINGS' ||
    type === 'START_GAME' ||
    type === 'SUBMIT_HAND' ||
    type === 'NEXT_ROUND' ||
    type === 'RETURN_TO_LOBBY' ||
    type === 'LEAVE' ||
    type === 'ADD_CPU' ||
    type === 'REMOVE_CPU'
  );
}

export function isServerMessageType(type: string): type is ServerMessageType {
  return (
    type === 'STATE_SYNC' ||
    type === 'LOBBY_UPDATE' ||
    type === 'SETTINGS_UPDATE' ||
    type === 'ROUND_START' ||
    type === 'SUBMISSION_UPDATE' ||
    type === 'ROUND_RESULT' ||
    type === 'MATCH_END' ||
    type === 'PLAYER_JOINED' ||
    type === 'PLAYER_LEFT' ||
    type === 'HOST_CHANGED' ||
    type === 'PONG' ||
    type === 'ERROR'
  );
}

/** Build a client envelope for `WebSocket.send`. */
export function makeClientEnvelope<K extends ClientMessageType>(
  type: K,
  payload: ClientPayloadMap[K],
): { type: K; payload: ClientPayloadMap[K]; v: WsProtocolVersion } {
  return { type, payload, v: WS_PROTOCOL_VERSION };
}
