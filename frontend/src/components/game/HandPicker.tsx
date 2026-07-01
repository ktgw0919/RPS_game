import { HAND_LABELS } from '@/lib/labels';
import type { Hand } from '@/types';

const HANDS: Hand[] = ['ROCK', 'SCISSORS', 'PAPER'];

interface HandPickerProps {
  disabled?: boolean;
  selected?: Hand | null;
  onPick: (hand: Hand) => void;
}

export function HandPicker({ disabled, selected, onPick }: HandPickerProps) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {HANDS.map((hand) => {
        const { emoji, label } = HAND_LABELS[hand];
        const active = selected === hand;
        return (
          <button
            key={hand}
            type="button"
            disabled={disabled}
            onClick={() => onPick(hand)}
            className={`flex min-h-[88px] flex-col items-center justify-center gap-1 rounded-xl border-2 text-center transition active:scale-[0.98] disabled:opacity-50 ${
              active
                ? 'border-indigo-400 bg-indigo-500/20'
                : 'border-slate-700 bg-slate-900 hover:border-slate-500'
            }`}
          >
            <span className="text-3xl" aria-hidden>
              {emoji}
            </span>
            <span className="text-sm font-semibold text-slate-200">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
