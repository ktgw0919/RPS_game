import { SpectatorBanner } from '@/components/game/SpectatorBanner';
import { Panel, PrimaryButton } from '@/components/ui/Panel';
import { useGame } from '@/hooks/useGame';
import { MATCH_END_REASON_LABELS } from '@/lib/labels';

export function MatchEndView() {
  const { state, send } = useGame();
  const { match, members, you, lastMatchEnd, room } = state;

  if (!match || !you || !room) return null;

  const isHost = you.is_host && you.player_id === room.host_player_id;
  const isSpectator = you.is_spectator;
  const nameById = new Map(members.map((m) => [m.player_id, m.display_name]));

  if (!lastMatchEnd) {
    return (
      <div className="flex flex-col gap-4">
        {isSpectator ? <SpectatorBanner /> : null}
        <Panel title="マッチ終了">
          <div className="flex flex-col gap-4">
            <p className="text-center text-sm text-slate-300">
              再接続しました。マッチは終了しています。
            </p>
            {isHost ? (
              <PrimaryButton onClick={() => send('RETURN_TO_LOBBY')}>ロビーへ戻る</PrimaryButton>
            ) : (
              <p className="text-center text-sm text-slate-400">
                ホストがロビーへ戻るのを待っています…
              </p>
            )}
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {isSpectator ? <SpectatorBanner /> : null}

      <Panel title="マッチ終了">
        <div className="flex flex-col gap-4">
          <p className="text-center text-sm text-slate-400">
            {MATCH_END_REASON_LABELS[lastMatchEnd.reason]}
          </p>

          {lastMatchEnd.winner_ids.length > 0 ? (
            <div className="text-center">
              <p className="text-xs text-slate-500">勝者</p>
              <p className="text-xl font-bold text-emerald-300">
                {lastMatchEnd.winner_ids.map((id) => nameById.get(id) ?? id).join('、')}
              </p>
            </div>
          ) : (
            <p className="text-center text-lg text-amber-300">引き分け終了</p>
          )}

          {Object.keys(lastMatchEnd.scores).length > 0 ? (
            <ul className="text-sm text-slate-300">
              {Object.entries(lastMatchEnd.scores).map(([id, score]) => (
                <li key={id} className="flex justify-between border-b border-slate-800 py-1">
                  <span>{nameById.get(id) ?? id}</span>
                  <span className="font-mono">{score}</span>
                </li>
              ))}
            </ul>
          ) : null}

          {isHost ? (
            <PrimaryButton onClick={() => send('RETURN_TO_LOBBY')}>ロビーへ戻る</PrimaryButton>
          ) : (
            <p className="text-center text-sm text-slate-400">
              ホストがロビーへ戻るのを待っています…
            </p>
          )}
        </div>
      </Panel>
    </div>
  );
}
