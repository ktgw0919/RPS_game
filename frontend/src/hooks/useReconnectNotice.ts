import { useEffect, useRef, useState } from 'react';

import { useGame } from '@/hooks/useGame';

/** Brief banner after WS reconnect succeeds (STATE_SYNC restores game state). */
export function useReconnectNotice(): string | null {
  const { state } = useGame();
  const { connectionStatus } = state;
  const prevStatus = useRef(connectionStatus);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (prevStatus.current === 'disconnected' && connectionStatus === 'connected') {
      setMessage('再接続しました。ゲーム状態を復元しています…');
      const id = window.setTimeout(() => setMessage(null), 4000);
      prevStatus.current = connectionStatus;
      return () => window.clearTimeout(id);
    }
    prevStatus.current = connectionStatus;
    return undefined;
  }, [connectionStatus]);

  return message;
}
