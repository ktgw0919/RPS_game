import { useContext } from 'react';

import { GameContext, type GameContextValue } from '@/context/GameContext';

export function useGame(): GameContextValue {
  const ctx = useContext(GameContext);
  if (!ctx) {
    throw new Error('useGame must be used within a GameProvider.');
  }
  return ctx;
}

/** Optional accessor for components that may render outside a room session. */
export function useOptionalGame(): GameContextValue | null {
  return useContext(GameContext);
}
