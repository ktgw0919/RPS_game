import { useCallback, useEffect, useState } from 'react';

import { HandButtonRow } from '@/components/lobby/CpuHandControls';
import { SecondaryButton } from '@/components/ui/Panel';
import { formatHandSequence } from '@/lib/cpuHands';
import type { Hand, PlayerView } from '@/types';

interface MemberListProps {
  members: PlayerView[];
  capacity: number;
  hostPlayerId: string | null;
  /** Host + ALLOW_CPU: show add/remove CPU controls (lobby only). */
  cpuControlsEnabled?: boolean;
  roomFull?: boolean;
  onAddRandomCpu?: () => void;
  onAddFixedCpu?: (hands: Hand[]) => void;
  onUpdateCpuHands?: (playerId: string, hands: Hand[]) => void;
  onRemoveCpu?: (playerId: string) => void;
  addCpuBusy?: boolean;
}

export function MemberList({
  members,
  capacity,
  hostPlayerId,
  cpuControlsEnabled = false,
  roomFull = false,
  onAddRandomCpu,
  onAddFixedCpu,
  onUpdateCpuHands,
  onRemoveCpu,
  addCpuBusy = false,
}: MemberListProps) {
  const [sequenceDraft, setSequenceDraft] = useState<Record<string, Hand[]>>({});

  const syncDraftFromMember = useCallback((member: PlayerView) => {
    if (member.cpu_strategy === 'FIXED' && member.cpu_fixed_hands?.length) {
      return member.cpu_fixed_hands;
    }
    return [];
  }, []);

  useEffect(() => {
    setSequenceDraft((prev) => {
      const next = { ...prev };
      for (const member of members) {
        if (!member.is_cpu) continue;
        if (!(member.player_id in next)) {
          next[member.player_id] = syncDraftFromMember(member);
        }
      }
      for (const id of Object.keys(next)) {
        if (!members.some((m) => m.player_id === id)) {
          delete next[id];
        }
      }
      return next;
    });
  }, [members, syncDraftFromMember]);

  const appendToDraft = (playerId: string, hand: Hand) => {
    setSequenceDraft((prev) => ({
      ...prev,
      [playerId]: [...(prev[playerId] ?? []), hand],
    }));
  };

  const applyDraft = (playerId: string) => {
    const hands = sequenceDraft[playerId] ?? [];
    if (hands.length === 0 || !onUpdateCpuHands) return;
    onUpdateCpuHands(playerId, hands);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm font-medium text-slate-300">
          参加者 ({members.length}/{capacity})
        </p>
        {cpuControlsEnabled && onAddRandomCpu ? (
          <div className="flex flex-col gap-2 sm:items-end">
            <SecondaryButton disabled={roomFull || addCpuBusy} onClick={onAddRandomCpu}>
              {addCpuBusy ? '追加中…' : '＋CPU（ランダム）'}
            </SecondaryButton>
            {onAddFixedCpu ? (
              <HandButtonRow
                prefix="＋CPU"
                size="sm"
                disabled={roomFull || addCpuBusy}
                onPick={(hand) => onAddFixedCpu([hand])}
              />
            ) : null}
          </div>
        ) : null}
      </div>
      <ul className="flex flex-col gap-2">
        {members.map((member) => {
          const draft = sequenceDraft[member.player_id] ?? [];
          const isFixed = member.cpu_strategy === 'FIXED';
          const displayHands = isFixed ? (member.cpu_fixed_hands ?? []) : [];

          return (
            <li
              key={member.player_id}
              className="flex flex-col gap-2 rounded-lg bg-slate-950/60 px-3 py-2 text-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 flex-1 items-center gap-2">
                  {member.is_cpu ? (
                    <span
                      className="shrink-0 rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-300"
                      title="CPU プレイヤー"
                    >
                      🤖 CPU
                    </span>
                  ) : null}
                  <span className="truncate font-medium text-slate-100">{member.display_name}</span>
                  {member.player_id === hostPlayerId ? (
                    <span className="shrink-0 rounded bg-indigo-500/20 px-1.5 py-0.5 text-xs text-indigo-300">
                      ホスト
                    </span>
                  ) : null}
                  {member.is_spectator ? (
                    <span className="shrink-0 rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-400">
                      観戦
                    </span>
                  ) : null}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {!member.is_cpu && member.connection_state === 'DISCONNECTED' ? (
                    <span className="text-xs text-amber-400">切断中</span>
                  ) : null}
                  {member.is_cpu && cpuControlsEnabled && onRemoveCpu ? (
                    <SecondaryButton onClick={() => onRemoveCpu(member.player_id)}>
                      削除
                    </SecondaryButton>
                  ) : null}
                </span>
              </div>

              {member.is_cpu && cpuControlsEnabled && onUpdateCpuHands ? (
                <div className="flex flex-col gap-2 border-t border-slate-800 pt-2">
                  <p className="text-xs text-slate-400">
                    {isFixed && displayHands.length > 0
                      ? `手の列: ${formatHandSequence(displayHands)}（ラウンドごとに繰り返し）`
                      : '手: ランダム'}
                  </p>
                  <HandButtonRow
                    prefix="単発"
                    size="sm"
                    onPick={(hand) => {
                      setSequenceDraft((prev) => ({ ...prev, [member.player_id]: [hand] }));
                      onUpdateCpuHands(member.player_id, [hand]);
                    }}
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <HandButtonRow
                      prefix="列に追加"
                      size="sm"
                      onPick={(hand) => appendToDraft(member.player_id, hand)}
                    />
                    <SecondaryButton
                      disabled={draft.length === 0}
                      onClick={() => applyDraft(member.player_id)}
                    >
                      列を適用
                    </SecondaryButton>
                    <SecondaryButton
                      onClick={() =>
                        setSequenceDraft((prev) => ({ ...prev, [member.player_id]: [] }))
                      }
                    >
                      下書きクリア
                    </SecondaryButton>
                  </div>
                  {draft.length > 0 ? (
                    <p className="text-xs text-violet-300">下書き: {formatHandSequence(draft)}</p>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
