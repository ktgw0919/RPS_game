import type { Hand } from '@/types';

import { HAND_LABELS } from '@/lib/labels';

export const CPU_HANDS: Hand[] = ['ROCK', 'SCISSORS', 'PAPER'];

export function formatHandSequence(hands: Hand[]): string {
  return hands.map((h) => HAND_LABELS[h].emoji).join(' → ');
}
