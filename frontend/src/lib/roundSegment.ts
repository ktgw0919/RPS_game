import type { MatchView, PlayerView, RuleType } from '@/types';

/** True when a round message applies to this viewer (§4 / TOURNAMENT pair filter). */
export function isViewerRoundMessage(
  match: MatchView | null,
  you: PlayerView | null,
  segmentId: string | null | undefined,
  alivePlayerIds: string[],
): boolean {
  if (!match || !you) return false;
  if (you.is_spectator) return true;
  if (match.rule_type !== 'TOURNAMENT') return true;
  if (!segmentId) return false;
  if (!alivePlayerIds.includes(you.player_id)) return false;
  if (match.segment_id != null) return segmentId === match.segment_id;
  return true;
}

export function ruleTypeLabel(ruleType: RuleType): string {
  switch (ruleType) {
    case 'MINORITY':
      return '少数派';
    case 'BOSS':
      return '代表';
    case 'TOURNAMENT':
      return 'トーナメント';
    default:
      return '通常';
  }
}
