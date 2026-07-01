import { useMemo } from 'react';

import { useGame } from '@/hooks/useGame';
import { FATAL_WS_ERROR_CODES } from '@/types';
import { formatWsError, NON_FATAL_OPERATION_ERROR_CODES } from '@/lib/wsErrorDisplay';

export interface OperationErrorNotice {
  message: string;
  dismiss: () => void;
}

/**
 * Non-fatal WS `ERROR` for in-room display (SessionNotices / host action feedback).
 * Fatal codes are handled by `useFatalSessionExit` instead.
 */
export function useOperationErrorNotice(): OperationErrorNotice | null {
  const { state, clearError } = useGame();
  const { lastError, connectionStatus } = state;

  return useMemo(() => {
    if (!lastError || connectionStatus !== 'connected') return null;
    if (FATAL_WS_ERROR_CODES.has(lastError.code)) return null;
    if (!NON_FATAL_OPERATION_ERROR_CODES.has(lastError.code)) return null;

    return {
      message: formatWsError(lastError),
      dismiss: clearError,
    };
  }, [lastError, connectionStatus, clearError]);
}
