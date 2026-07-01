import { useEffect, useRef, useState } from 'react';

import { useGame } from '@/hooks/useGame';

/** Toast when `LOBBY_UPDATE` / `STATE_SYNC` reports a new host (§10 host transfer). */
export function useHostTransferNotice(): string | null {
  const { state } = useGame();
  const { room, members } = state;
  const hostId = room?.host_player_id ?? null;
  const prevHostId = useRef<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!hostId) {
      prevHostId.current = hostId;
      return;
    }

    if (prevHostId.current && prevHostId.current !== hostId) {
      const newHost = members.find((m) => m.player_id === hostId);
      const label = newHost?.display_name ?? '新しいホスト';
      setMessage(`${label} がホストになりました`);
      const id = window.setTimeout(() => setMessage(null), 5000);
      prevHostId.current = hostId;
      return () => window.clearTimeout(id);
    }

    prevHostId.current = hostId;
    return undefined;
  }, [hostId, members]);

  return message;
}
