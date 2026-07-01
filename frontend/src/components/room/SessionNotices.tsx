import { useHostTransferNotice } from '@/hooks/useHostTransferNotice';
import { useReconnectNotice } from '@/hooks/useReconnectNotice';

export function SessionNotices() {
  const reconnect = useReconnectNotice();
  const hostTransfer = useHostTransferNotice();

  if (!reconnect && !hostTransfer) return null;

  return (
    <div className="flex flex-col gap-2">
      {reconnect ? (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          {reconnect}
        </div>
      ) : null}
      {hostTransfer ? (
        <div className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-3 py-2 text-xs text-indigo-200">
          {hostTransfer}
        </div>
      ) : null}
    </div>
  );
}
