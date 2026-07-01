import type { MatchView, PlayerView } from '@/types';

import { ruleTypeLabel } from '@/lib/roundSegment';

interface RuleStatusBannerProps {
  match: MatchView;
  members: PlayerView[];
}

export function RuleStatusBanner({ match, members }: RuleStatusBannerProps) {
  const bossName =
    match.boss_player_id != null
      ? (members.find((m) => m.player_id === match.boss_player_id)?.display_name ?? 'ボス')
      : null;

  if (match.rule_type === 'MINORITY') {
    return (
      <div className="rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2 text-sm text-violet-100">
        <p className="font-medium">{ruleTypeLabel('MINORITY')}ルール</p>
        <p className="text-xs text-violet-200/80">
          生存者 {match.alive_player_ids.length} 人
          {match.switched_to_normal_finish ? ' — 通常じゃんけんで決着中' : ''}
        </p>
      </div>
    );
  }

  if (match.rule_type === 'BOSS' && bossName) {
    return (
      <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-100">
        <p className="font-medium">
          {ruleTypeLabel('BOSS')}ルール — ボス: {bossName}
        </p>
        {Object.keys(match.scores).length > 0 ? (
          <p className="text-xs text-rose-200/80">得点はラウンド結果に表示されます</p>
        ) : null}
      </div>
    );
  }

  if (match.rule_type === 'TOURNAMENT') {
    return (
      <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100">
        <p className="font-medium">{ruleTypeLabel('TOURNAMENT')}ルール</p>
        {match.segment_id ? (
          <p className="text-xs text-cyan-200/80">あなたのペア: {match.segment_id}</p>
        ) : (
          <p className="text-xs text-cyan-200/80">他ペアの対戦を待っています</p>
        )}
      </div>
    );
  }

  return null;
}
