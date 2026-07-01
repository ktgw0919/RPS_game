import { useState } from 'react';

import { Panel, SecondaryButton } from '@/components/ui/Panel';
import { useMatchHistory } from '@/hooks/useMatchHistory';
import { ApiRequestError } from '@/lib/api';
import { RULE_LABELS } from '@/lib/labels';
import type { IsoDateTime, MatchHistoryEntry } from '@/types';

interface MatchHistoryPanelProps {
  roomCode: string;
}

function formatEndedAtLocal(endedAt: IsoDateTime): string {
  return new Date(endedAt).toLocaleString(undefined, {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function playerLabel(
  playerId: string,
  players: MatchHistoryEntry['players'],
): string {
  const player = players.find((p) => p.player_id === playerId);
  if (!player) return playerId;
  return player.is_cpu ? `${player.display_name} 🤖` : player.display_name;
}

function formatWinners(entry: MatchHistoryEntry): string {
  if (entry.winner_ids.length === 0) return '引き分け';
  return entry.winner_ids.map((id) => playerLabel(id, entry.players)).join('、');
}

function formatScores(entry: MatchHistoryEntry): string | null {
  const rows = Object.entries(entry.scores);
  if (rows.length === 0) return null;
  return rows
    .map(([id, score]) => `${playerLabel(id, entry.players)}: ${score}`)
    .join(' / ');
}

function HistoryRow({
  entry,
  index,
  total,
}: {
  entry: MatchHistoryEntry;
  index: number;
  total: number;
}) {
  const scores = formatScores(entry);

  return (
    <li className="rounded-lg bg-slate-950/60 px-3 py-2 text-sm">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-mono text-xs text-slate-500">#{total - index}</span>
        <span className="font-medium text-slate-200">{RULE_LABELS[entry.rule_type]}</span>
        <span className="text-xs text-slate-500">{formatEndedAtLocal(entry.ended_at)}</span>
      </div>
      <p className="mt-1 text-slate-300">
        勝者: <span className="text-slate-100">{formatWinners(entry)}</span>
      </p>
      {scores ? <p className="mt-0.5 text-xs text-slate-400">得点: {scores}</p> : null}
    </li>
  );
}

export function MatchHistoryPanel({ roomCode }: MatchHistoryPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const { data, error, isLoading, isValidating, refresh } = useMatchHistory(roomCode, {
    enabled: true,
  });

  const handleRefresh = () => {
    void refresh();
  };

  const matches = data?.matches ?? [];
  const showSpinner = isLoading && !data;
  const showError = Boolean(error) && !data;

  return (
    <Panel>
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex min-w-0 flex-1 items-center justify-between text-left text-sm font-semibold text-slate-200"
          aria-expanded={expanded}
        >
          <span>対戦履歴</span>
          <span className="shrink-0 text-slate-500" aria-hidden>
            {expanded ? '▲' : '▼'}
          </span>
        </button>
        <span className="shrink-0">
          <SecondaryButton
            disabled={isValidating}
            onClick={handleRefresh}
            aria-label="対戦履歴を更新"
          >
            {isValidating ? '更新中…' : '更新'}
          </SecondaryButton>
        </span>
      </div>

      {expanded ? (
        <div className="mt-4 border-t border-slate-800 pt-4">
          {showSpinner ? (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-slate-400">
              <span
                className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent"
                aria-hidden
              />
              読み込み中…
            </div>
          ) : null}

          {showError ? (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <p className="text-sm text-amber-300">履歴を読み込めませんでした</p>
              {error instanceof ApiRequestError && error.code === 'SERVICE_UNAVAILABLE' ? (
                <p className="text-xs text-slate-500">サーバーが一時的に利用できません</p>
              ) : null}
              <SecondaryButton onClick={handleRefresh}>再試行</SecondaryButton>
            </div>
          ) : null}

          {!showSpinner && !showError && matches.length === 0 ? (
            <p className="py-4 text-center text-sm text-slate-500">まだ対戦履歴がありません</p>
          ) : null}

          {!showSpinner && !showError && matches.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {matches.map((entry, index) => (
                <HistoryRow
                  key={entry.match_id}
                  entry={entry}
                  index={index}
                  total={matches.length}
                />
              ))}
            </ul>
          ) : null}

          {data?.has_more ? (
            <p className="mt-3 text-center text-xs text-slate-500">
              さらに古い履歴があります（直近 {matches.length} 件を表示）
            </p>
          ) : null}
        </div>
      ) : null}
    </Panel>
  );
}
