/**
 * WebSocket hook for the realtime game loop (ARCHITECTURE.md §4).
 *
 * Owns the socket lifecycle: connect, JOIN auth, heartbeat PING/PONG, inbound
 * envelope parsing, and dispatching reducer actions. Fatal `ERROR` codes close
 * the socket; transient disconnects schedule a reconnect with backoff.
 */

import { useCallback, useEffect, useRef, type Dispatch } from 'react';

import { HEARTBEAT_INTERVAL_SEC, WS_PROTOCOL_VERSION } from '@/lib/constants';
import type { GameAction } from '@/reducers/gameReducer';
import {
  FATAL_WS_ERROR_CODES,
  isEnvelope,
  makeClientEnvelope,
  type ClientMessageType,
  type ClientPayloadMap,
  type Envelope,
  type ErrorPayload,
  type LobbyUpdatePayload,
  type MatchEndPayload,
  type RoundResultPayload,
  type RoundStartPayload,
  type SettingsUpdatePayload,
  type StateSyncPayload,
  type SubmissionUpdatePayload,
} from '@/types';

const MAX_RECONNECT_DELAY_MS = 30_000;

export interface UseWebSocketOptions {
  roomCode: string;
  playerToken: string;
  enabled?: boolean;
  dispatch: Dispatch<GameAction>;
}

export interface UseWebSocketResult {
  /** Send a client envelope; no-op when the socket is not open. */
  send: <K extends ClientMessageType>(
    type: K,
    ...args: ClientPayloadMap[K] extends EmptyPayloadLike ? [] : [payload: ClientPayloadMap[K]]
  ) => void;
  /** Close the socket and suppress auto-reconnect until the hook remounts. */
  disconnect: () => void;
}

type EmptyPayloadLike = Record<string, never>;

function wsUrl(roomCode: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/rooms/${encodeURIComponent(roomCode)}`;
}

function dispatchServerMessage(dispatch: Dispatch<GameAction>, message: Envelope): void {
  switch (message.type) {
    case 'STATE_SYNC':
      dispatch({ type: 'STATE_SYNC', payload: message.payload as StateSyncPayload });
      break;
    case 'LOBBY_UPDATE':
      dispatch({ type: 'LOBBY_UPDATE', payload: message.payload as LobbyUpdatePayload });
      break;
    case 'SETTINGS_UPDATE':
      dispatch({ type: 'SETTINGS_UPDATE', payload: message.payload as SettingsUpdatePayload });
      break;
    case 'ROUND_START':
      dispatch({ type: 'ROUND_START', payload: message.payload as RoundStartPayload });
      break;
    case 'SUBMISSION_UPDATE':
      dispatch({
        type: 'SUBMISSION_UPDATE',
        payload: message.payload as SubmissionUpdatePayload,
      });
      break;
    case 'ROUND_RESULT':
      dispatch({ type: 'ROUND_RESULT', payload: message.payload as RoundResultPayload });
      break;
    case 'MATCH_END':
      dispatch({ type: 'MATCH_END', payload: message.payload as MatchEndPayload });
      break;
    case 'ERROR': {
      const payload = message.payload as ErrorPayload;
      dispatch({ type: 'WS_ERROR', payload });
      break;
    }
    case 'PLAYER_JOINED':
    case 'PLAYER_LEFT':
    case 'HOST_CHANGED':
      break;
    case 'PONG':
      break;
    default:
      break;
  }
}

export function useWebSocket({
  roomCode,
  playerToken,
  enabled = true,
  dispatch,
}: UseWebSocketOptions): UseWebSocketResult {
  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const intentionalCloseRef = useRef(false);
  const fatalRef = useRef(false);

  const clearHeartbeat = useCallback(() => {
    if (heartbeatRef.current !== null) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  }, []);

  const clearReconnect = useCallback(() => {
    if (reconnectRef.current !== null) {
      clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
    }
  }, []);

  const send = useCallback(
    <K extends ClientMessageType>(
      type: K,
      ...args: ClientPayloadMap[K] extends EmptyPayloadLike ? [] : [payload: ClientPayloadMap[K]]
    ) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      const payload = (args[0] ?? {}) as ClientPayloadMap[K];
      ws.send(JSON.stringify(makeClientEnvelope(type, payload)));
    },
    [],
  );

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    clearHeartbeat();
    clearReconnect();
    wsRef.current?.close();
    wsRef.current = null;
    dispatch({ type: 'CONNECTION_STATUS', status: 'idle' });
  }, [clearHeartbeat, clearReconnect, dispatch]);

  useEffect(() => {
    if (!enabled || !roomCode || !playerToken) {
      dispatch({ type: 'CONNECTION_STATUS', status: 'idle' });
      return;
    }

    intentionalCloseRef.current = false;
    fatalRef.current = false;
    attemptRef.current = 0;

    const connect = () => {
      if (intentionalCloseRef.current || fatalRef.current) return;

      clearReconnect();
      dispatch({ type: 'CONNECTION_STATUS', status: 'connecting' });

      const ws = new WebSocket(wsUrl(roomCode));
      wsRef.current = ws;

      ws.addEventListener('open', () => {
        attemptRef.current = 0;
        dispatch({ type: 'CONNECTION_STATUS', status: 'connected' });
        send('JOIN', { token: playerToken });

        clearHeartbeat();
        heartbeatRef.current = setInterval(() => {
          send('PING');
        }, HEARTBEAT_INTERVAL_SEC * 1000);
      });

      ws.addEventListener('message', (event) => {
        let parsed: unknown;
        try {
          parsed = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (!isEnvelope(parsed) || parsed.v !== WS_PROTOCOL_VERSION) return;

        if (parsed.type === 'ERROR') {
          const payload = parsed.payload as ErrorPayload;
          dispatchServerMessage(dispatch, parsed);
          if (FATAL_WS_ERROR_CODES.has(payload.code)) {
            fatalRef.current = true;
            intentionalCloseRef.current = true;
            if (payload.code === 'SESSION_REPLACED') {
              dispatch({ type: 'CONNECTION_STATUS', status: 'replaced' });
            } else {
              dispatch({ type: 'CONNECTION_STATUS', status: 'disconnected' });
            }
            clearHeartbeat();
            ws.close();
          }
          return;
        }

        dispatchServerMessage(dispatch, parsed);
      });

      ws.addEventListener('close', () => {
        clearHeartbeat();
        wsRef.current = null;
        if (intentionalCloseRef.current || fatalRef.current) return;

        dispatch({ type: 'CONNECTION_STATUS', status: 'disconnected' });
        attemptRef.current += 1;
        const delay = Math.min(1000 * 2 ** attemptRef.current, MAX_RECONNECT_DELAY_MS);
        reconnectRef.current = setTimeout(connect, delay);
      });

      ws.addEventListener('error', () => {
        // `close` follows; reconnect is handled there.
      });
    };

    connect();

    return () => {
      intentionalCloseRef.current = true;
      clearHeartbeat();
      clearReconnect();
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [roomCode, playerToken, enabled, dispatch, send, clearHeartbeat, clearReconnect]);

  return { send, disconnect };
}
