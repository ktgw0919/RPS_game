import { useCallback } from 'react';

import { useGame } from '@/hooks/useGame';
import { clearSession } from '@/lib/session';

/** `LEAVE` → disconnect → clear session (ARCHITECTURE.md §3 / SCREENS.md §5). */
export function useExitRoom() {
  const { send, disconnect } = useGame();

  const exitCurrentRoom = useCallback(async () => {
    send('LEAVE');
    disconnect();
    clearSession();
  }, [send, disconnect]);

  return { exitCurrentRoom };
}
