import { useGame } from '@/hooks/useGame';
import { FATAL_WS_ERROR_CODES } from '@/types';

export function ConnectionBanner() {
  const { state } = useGame();
  const { connectionStatus, lastError } = state;

  if (connectionStatus === 'connected' && !lastError) return null;

  let message: string | null = null;
  let tone: 'warn' | 'error' | 'info' = 'error';

  if (connectionStatus === 'connecting') {
    message = '接続中…';
    tone = 'info';
  } else if (connectionStatus === 'disconnected') {
    message = '切断されました。再接続を試みています…';
    tone = 'warn';
  } else if (connectionStatus === 'replaced') {
    message = '別の端末で同じアカウントが接続されました。';
  } else if (lastError && !FATAL_WS_ERROR_CODES.has(lastError.code)) {
    message = `${lastError.code}: ${lastError.message}`;
    tone = 'warn';
  }

  if (!message) return null;

  const styles =
    tone === 'info'
      ? 'border-slate-600/40 bg-slate-800/60 text-slate-300'
      : tone === 'warn'
        ? 'border-amber-500/40 bg-amber-500/10 text-amber-200'
        : 'border-rose-500/40 bg-rose-500/10 text-rose-200';

  return (
    <div className={`rounded-lg border px-3 py-2 text-xs ${styles}`} role="status">
      {message}
    </div>
  );
}
