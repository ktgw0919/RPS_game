/**
 * Game state reducer (ARCHITECTURE.md §4 / frontend.mdc).
 *
 * `STATE_SYNC` is an authoritative snapshot that fully resets live game state.
 * `LOBBY_UPDATE` / `SETTINGS_UPDATE` replace roster or config. Round/match
 * messages apply incremental patches on top.
 */

import { deriveRoundTiming, matchAfterRoundStart } from '@/lib/gameView';
import type {
  ErrorPayload,
  LobbyUpdatePayload,
  MatchConfig,
  MatchEndPayload,
  MatchView,
  PlayerView,
  RoomView,
  RoundResultPayload,
  RoundStartPayload,
  SettingsUpdatePayload,
  StateSyncPayload,
  SubmissionUpdatePayload,
  WsConnectionStatus,
} from '@/types';

export interface GameState {
  room: RoomView | null;
  members: PlayerView[];
  you: PlayerView | null;
  match: MatchView | null;
  config: MatchConfig | null;
  /** Latest server clock anchor for deadline math (§4). */
  serverNow: string | null;
  roundTiming: Pick<
    RoundStartPayload,
    'round_no' | 'deadline_at' | 'server_now' | 'alive_player_ids'
  > | null;
  submissionProgress: Pick<
    SubmissionUpdatePayload,
    'round_no' | 'submitted_player_ids' | 'expected_count'
  > | null;
  lastRoundResult: RoundResultPayload | null;
  lastMatchEnd: MatchEndPayload | null;
  connectionStatus: WsConnectionStatus;
  lastError: ErrorPayload | null;
}

export type GameAction =
  | { type: 'STATE_SYNC'; payload: StateSyncPayload }
  | { type: 'LOBBY_UPDATE'; payload: LobbyUpdatePayload }
  | { type: 'SETTINGS_UPDATE'; payload: SettingsUpdatePayload }
  | { type: 'ROUND_START'; payload: RoundStartPayload }
  | { type: 'SUBMISSION_UPDATE'; payload: SubmissionUpdatePayload }
  | { type: 'ROUND_RESULT'; payload: RoundResultPayload }
  | { type: 'MATCH_END'; payload: MatchEndPayload }
  | { type: 'WS_ERROR'; payload: ErrorPayload }
  | { type: 'CONNECTION_STATUS'; status: WsConnectionStatus }
  | { type: 'RESET' };

export const initialGameState: GameState = {
  room: null,
  members: [],
  you: null,
  match: null,
  config: null,
  serverNow: null,
  roundTiming: null,
  submissionProgress: null,
  lastRoundResult: null,
  lastMatchEnd: null,
  connectionStatus: 'idle',
  lastError: null,
};

function syncYou(members: PlayerView[], current: PlayerView | null): PlayerView | null {
  if (!current) return null;
  return members.find((m) => m.player_id === current.player_id) ?? current;
}

export function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {
    case 'RESET':
      return { ...initialGameState };

    case 'CONNECTION_STATUS':
      return { ...state, connectionStatus: action.status };

    case 'WS_ERROR':
      return { ...state, lastError: action.payload };

    case 'STATE_SYNC': {
      const { room, members, you, match, server_now } = action.payload;
      const roundTiming = deriveRoundTiming(match, server_now);
      return {
        ...initialGameState,
        room,
        members,
        you,
        match,
        config: room.config,
        serverNow: server_now,
        roundTiming,
        connectionStatus: state.connectionStatus,
        lastError: null,
      };
    }

    case 'LOBBY_UPDATE': {
      const { members, host_player_id, config } = action.payload;
      const you = syncYou(members, state.you);
      const returnedToLobby = state.match?.state === 'MATCH_END';
      const roundTiming =
        !returnedToLobby && state.match && state.serverNow
          ? (deriveRoundTiming(state.match, state.serverNow) ?? state.roundTiming)
          : null;
      const room = state.room
        ? {
            ...state.room,
            host_player_id,
            config,
            member_count: members.length,
            ...(returnedToLobby ? { status: 'WAITING' as const } : {}),
          }
        : null;
      return {
        ...state,
        members,
        you,
        room,
        config,
        match: returnedToLobby ? null : state.match,
        lastMatchEnd: returnedToLobby ? null : state.lastMatchEnd,
        lastRoundResult: returnedToLobby ? null : state.lastRoundResult,
        roundTiming: returnedToLobby ? null : roundTiming,
        submissionProgress: returnedToLobby ? null : state.submissionProgress,
      };
    }

    case 'SETTINGS_UPDATE':
      return {
        ...state,
        config: action.payload.config,
        room: state.room ? { ...state.room, config: action.payload.config } : null,
      };

    case 'ROUND_START': {
      const payload = action.payload;
      const config = state.config ?? state.room?.config ?? null;
      const match = matchAfterRoundStart(state.match, config, payload);
      const room = state.room ? { ...state.room, status: 'IN_GAME' as const } : null;
      return {
        ...state,
        room,
        match,
        serverNow: payload.server_now,
        roundTiming: {
          round_no: payload.round_no,
          deadline_at: payload.deadline_at,
          server_now: payload.server_now,
          alive_player_ids: payload.alive_player_ids,
        },
        submissionProgress: null,
        lastRoundResult: null,
      };
    }

    case 'SUBMISSION_UPDATE': {
      const payload = action.payload;
      const myId = state.you?.player_id;
      const mySubmitted = myId ? payload.submitted_player_ids.includes(myId) : false;
      const match = state.match ? { ...state.match, my_submitted: mySubmitted } : null;
      return {
        ...state,
        match,
        submissionProgress: {
          round_no: payload.round_no,
          submitted_player_ids: payload.submitted_player_ids,
          expected_count: payload.expected_count,
        },
      };
    }

    case 'ROUND_RESULT': {
      const payload = action.payload;
      const match = state.match
        ? {
            ...state.match,
            state: 'ROUND_RESULT' as const,
            alive_player_ids: payload.alive_player_ids,
            scores: payload.scores,
          }
        : null;
      return { ...state, match, lastRoundResult: payload };
    }

    case 'MATCH_END': {
      const payload = action.payload;
      const match = state.match
        ? {
            ...state.match,
            state: 'MATCH_END' as const,
            scores: payload.scores,
          }
        : null;
      return { ...state, match, lastMatchEnd: payload };
    }

    default:
      return state;
  }
}
