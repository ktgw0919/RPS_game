/**
 * Game state context (ARCHITECTURE.md §1 / frontend.mdc).
 *
 * Combines `useReducer` game state with `useWebSocket` transport. UI layers
 * read state via `useGame()` and send client messages through `send()`.
 */

import { createContext, useCallback, useMemo, useReducer, type ReactNode } from 'react';

import { useWebSocket } from '@/hooks/useWebSocket';
import { gameReducer, initialGameState, type GameState } from '@/reducers/gameReducer';
import type { ClientMessageType, ClientPayloadMap } from '@/types';

export interface GameContextValue {
  state: GameState;
  send: <K extends ClientMessageType>(
    type: K,
    ...args: ClientPayloadMap[K] extends Record<string, never> ? [] : [payload: ClientPayloadMap[K]]
  ) => void;
  disconnect: () => void;
  reset: () => void;
  clearError: () => void;
}

const GameContext = createContext<GameContextValue | null>(null);

export { GameContext };

export interface GameProviderProps {
  children: ReactNode;
  roomCode: string;
  playerToken: string;
  /** When false, the socket stays idle (e.g. before REST join completes). */
  enabled?: boolean;
}

export function GameProvider({
  children,
  roomCode,
  playerToken,
  enabled = true,
}: GameProviderProps) {
  const [state, dispatch] = useReducer(gameReducer, initialGameState);
  const { send, disconnect } = useWebSocket({
    roomCode,
    playerToken,
    enabled,
    dispatch,
  });

  const reset = useCallback(() => {
    dispatch({ type: 'RESET' });
  }, []);

  const clearError = useCallback(() => {
    dispatch({ type: 'CLEAR_ERROR' });
  }, []);

  const value = useMemo<GameContextValue>(
    () => ({ state, send, disconnect, reset, clearError }),
    [state, send, disconnect, reset, clearError],
  );

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
}
