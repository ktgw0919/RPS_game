import { useHostTransferNotice } from '@/hooks/useHostTransferNotice';
import { useOperationErrorNotice } from '@/hooks/useOperationErrorNotice';
import { useReconnectNotice } from '@/hooks/useReconnectNotice';

export function SessionNotices() {
  const reconnect = useReconnectNotice();
  const hostTransfer = useHostTransferNotice();
  const operationError = useOperationErrorNotice();

  if (!reconnect && !hostTransfer && !operationError) return null;

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
      {operationError ? (
        <div
          className="flex items-start justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
          role="alert"
        >
          <span>{operationError.message}</span>
          <button
            type="button"
            onClick={operationError.dismiss}
            className="shrink-0 text-amber-300/80 underline hover:text-amber-200"
          >
            閉じる
          </button>
        </div>
      ) : null}
    </div>
  );
}
