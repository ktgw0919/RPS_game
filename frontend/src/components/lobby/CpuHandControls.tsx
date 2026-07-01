import type { Hand } from '@/types';

import { CPU_HANDS } from '@/lib/cpuHands';
import { HAND_LABELS } from '@/lib/labels';

interface HandButtonRowProps {
  onPick: (hand: Hand) => void;
  prefix?: string;
  size?: 'sm' | 'md';
  disabled?: boolean;
}

export function HandButtonRow({
  onPick,
  prefix = '',
  size = 'md',
  disabled = false,
}: HandButtonRowProps) {
  const pad = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm';
  return (
    <span className="flex flex-wrap items-center gap-1">
      {prefix ? <span className="text-xs text-slate-500">{prefix}</span> : null}
      {CPU_HANDS.map((hand) => {
        const meta = HAND_LABELS[hand];
        return (
          <button
            key={hand}
            type="button"
            disabled={disabled}
            title={meta.label}
            onClick={() => onPick(hand)}
            className={`rounded border border-slate-600 bg-slate-800/80 text-slate-100 hover:bg-slate-700 disabled:opacity-40 ${pad}`}
          >
            {meta.emoji}
          </button>
        );
      })}
    </span>
  );
}
