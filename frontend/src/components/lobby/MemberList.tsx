import { SecondaryButton } from '@/components/ui/Panel';
import type { PlayerView } from '@/types';

interface MemberListProps {
  members: PlayerView[];
  capacity: number;
  hostPlayerId: string | null;
  /** Host + ALLOW_CPU: show add/remove CPU controls (lobby only). */
  cpuControlsEnabled?: boolean;
  roomFull?: boolean;
  onAddCpu?: () => void;
  onRemoveCpu?: (playerId: string) => void;
  addCpuBusy?: boolean;
}

export function MemberList({
  members,
  capacity,
  hostPlayerId,
  cpuControlsEnabled = false,
  roomFull = false,
  onAddCpu,
  onRemoveCpu,
  addCpuBusy = false,
}: MemberListProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-slate-300">
          参加者 ({members.length}/{capacity})
        </p>
        {cpuControlsEnabled && onAddCpu ? (
          <SecondaryButton disabled={roomFull || addCpuBusy} onClick={onAddCpu}>
            {addCpuBusy ? '追加中…' : '＋CPUを追加'}
          </SecondaryButton>
        ) : null}
      </div>
      <ul className="flex flex-col gap-2">
        {members.map((member) => (
          <li
            key={member.player_id}
            className="flex items-center justify-between gap-2 rounded-lg bg-slate-950/60 px-3 py-2 text-sm"
          >
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
          </li>
        ))}
      </ul>
    </div>
  );
}
