import { formatCountdown, useDeadline } from '@/hooks/useDeadline';

interface DeadlineTimerProps {
  serverNow: string | null;
  deadlineAt: string | null;
}

export function DeadlineTimer({ serverNow, deadlineAt }: DeadlineTimerProps) {
  const msLeft = useDeadline(serverNow, deadlineAt);
  const urgent = msLeft !== null && msLeft <= 3000;

  return (
    <div
      className={`rounded-xl border px-4 py-3 text-center ${
        urgent ? 'border-rose-500/50 bg-rose-500/10' : 'border-slate-700 bg-slate-900/60'
      }`}
    >
      <p className="text-xs text-slate-400">残り時間</p>
      <p className={`font-mono text-3xl font-bold ${urgent ? 'text-rose-300' : 'text-white'}`}>
        {formatCountdown(msLeft)}
      </p>
    </div>
  );
}
