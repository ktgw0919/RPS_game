import type { Hand, MatchEndReason, NormalEndMode, RoundAdvanceMode, RuleType } from '@/types';

export const HAND_LABELS: Record<Hand, { emoji: string; label: string }> = {
  ROCK: { emoji: '✊', label: 'グー' },
  SCISSORS: { emoji: '✌️', label: 'チョキ' },
  PAPER: { emoji: '✋', label: 'パー' },
};

export const RULE_LABELS: Record<RuleType, string> = {
  NORMAL: '通常',
  MINORITY: '少数派',
  BOSS: '代表',
  TOURNAMENT: 'トーナメント',
};

export const NORMAL_END_LABELS: Record<NormalEndMode, string> = {
  ELIMINATION: '脱落式',
  SINGLE_ROUND: '1ラウンド確定',
};

export const ADVANCE_MODE_LABELS: Record<RoundAdvanceMode, string> = {
  AUTO: '自動',
  MANUAL: '手動',
};

export const MATCH_END_REASON_LABELS: Record<MatchEndReason, string> = {
  DECIDED: '決着',
  DRAW_MAX_ROUNDS: 'あいこ上限',
};
