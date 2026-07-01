/**
 * MatchConfig UI limits (ARCHITECTURE.md §9 — authoritative ranges).
 */

import type { MatchConfig, RuleType } from '@/types';

export const MATCH_CONFIG_LIMITS = {
  round_time_limit_sec: { min: 5, max: 60, step: 5 },
  result_display_sec: { min: 1, max: 10, step: 1 },
  max_draw_rounds: { min: 1, max: 20, step: 1 },
  minority_finish_threshold: { min: 2 },
} as const;

const MIN_PLAYERS_BY_RULE: Record<RuleType, number> = {
  NORMAL: 2,
  MINORITY: 3,
  BOSS: 2,
  TOURNAMENT: 2,
};

/** Set S: non-spectators that are CONNECTED or CPU (ARCHITECTURE.md §4.2). */
export function eligiblePlayerIds(
  members: {
    player_id: string;
    is_spectator: boolean;
    is_cpu: boolean;
    connection_state: string;
  }[],
): string[] {
  return members
    .filter((m) => !m.is_spectator && (m.is_cpu || m.connection_state === 'CONNECTED'))
    .map((m) => m.player_id);
}

export function minPlayersFor(ruleType: RuleType): number {
  return MIN_PLAYERS_BY_RULE[ruleType];
}

/** UX hint for why start is disabled; server re-validates on START_GAME. */
export function getStartBlockReason(
  members: {
    player_id: string;
    is_spectator: boolean;
    is_cpu: boolean;
    connection_state: string;
  }[],
  config: MatchConfig,
): string | null {
  const eligible = eligiblePlayerIds(members);
  const min = minPlayersFor(config.rule_type);

  if (eligible.length < min) {
    return `開始には ${min} 人以上必要です（参加可能 ${eligible.length} 人）`;
  }

  if (config.rule_type === 'BOSS') {
    if (!config.boss_player_id) return '代表ルールではボスを選択してください';
    if (!eligible.includes(config.boss_player_id)) return '選択したボスがルームにいません';
  }

  if (config.rule_type === 'MINORITY') {
    const maxThreshold = Math.max(
      MATCH_CONFIG_LIMITS.minority_finish_threshold.min,
      eligible.length - 1,
    );
    if (config.minority_finish_threshold > maxThreshold) {
      return '少数派閾値が参加者数に対して大きすぎます';
    }
  }

  return null;
}

export function canStartGame(
  members: {
    player_id: string;
    is_spectator: boolean;
    is_cpu: boolean;
    connection_state: string;
  }[],
  config: MatchConfig,
): boolean {
  return getStartBlockReason(members, config) === null;
}
