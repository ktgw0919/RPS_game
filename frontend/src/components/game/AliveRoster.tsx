import type { PlayerView } from '@/types';

interface AliveRosterProps {
  members: PlayerView[];
  alivePlayerIds: string[];
}

/** In-game roster: alive players and connection state (§7 disconnect visibility). */
export function AliveRoster({ members, alivePlayerIds }: AliveRosterProps) {
  const alive = members.filter((m) => alivePlayerIds.includes(m.player_id));

  if (alive.length === 0) return null;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
      <p className="mb-2 text-xs font-medium text-slate-500">生存者</p>
      <ul className="flex flex-wrap gap-2">
        {alive.map((m) => (
          <li
            key={m.player_id}
            className={`rounded-full px-2.5 py-1 text-xs ${
              m.connection_state === 'DISCONNECTED'
                ? 'bg-amber-500/15 text-amber-200'
                : 'bg-slate-800 text-slate-200'
            }`}
          >
            {m.display_name}
            {m.connection_state === 'DISCONNECTED' ? ' · 切断中' : ''}
          </li>
        ))}
      </ul>
    </div>
  );
}
