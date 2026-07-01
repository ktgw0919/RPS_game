import { useEffect, useRef, useState } from 'react';

import { remainingMs } from '@/types';

/**
 * Live countdown from authoritative `server_now` / `deadline_at` (§4).
 * Does not rely on the device clock for the anchor — only for elapsed drift.
 */
export function useDeadline(serverNow: string | null, deadlineAt: string | null): number | null {
  const anchorRef = useRef<number>(Date.now());
  const [msLeft, setMsLeft] = useState<number | null>(null);

  useEffect(() => {
    if (!serverNow || !deadlineAt) {
      setMsLeft(null);
      return;
    }

    anchorRef.current = Date.now();
    const baseRemaining = remainingMs(serverNow, deadlineAt);

    const tick = () => {
      const elapsed = Date.now() - anchorRef.current;
      setMsLeft(Math.max(0, baseRemaining - elapsed));
    };

    tick();
    const id = window.setInterval(tick, 100);
    return () => window.clearInterval(id);
  }, [serverNow, deadlineAt]);

  return msLeft;
}

export function formatCountdown(ms: number | null): string {
  if (ms === null) return '—';
  if (ms <= 0) return '締切';
  const totalSec = Math.ceil(ms / 1000);
  return `${totalSec}秒`;
}
