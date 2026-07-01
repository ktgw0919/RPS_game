import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import { useGame } from '@/hooks/useGame';
import { clearSession } from '@/lib/session';
import { FATAL_WS_ERROR_CODES } from '@/types';

/** Leave room and return home on fatal WS errors or session replacement. */
export function useFatalSessionExit(): void {
  const { state, disconnect, reset } = useGame();
  const navigate = useNavigate();

  useEffect(() => {
    const code = state.lastError?.code;
    const fatalError = code !== undefined && FATAL_WS_ERROR_CODES.has(code);
    const replaced = state.connectionStatus === 'replaced';

    if (!fatalError && !replaced) return;

    disconnect();
    reset();
    clearSession();
    navigate('/', {
      replace: true,
      state: {
        message:
          state.lastError?.message ??
          (replaced ? '別の端末で接続されたため、このセッションは終了しました。' : undefined),
      },
    });
  }, [state.connectionStatus, state.lastError, disconnect, reset, navigate]);
}
