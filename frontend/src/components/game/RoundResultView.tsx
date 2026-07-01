import { AliveRoster } from '@/components/game/AliveRoster';
import { RuleStatusBanner } from '@/components/game/RuleStatusBanner';
import { SpectatorBanner } from '@/components/game/SpectatorBanner';
import { Panel, PrimaryButton } from '@/components/ui/Panel';
import { useGame } from '@/hooks/useGame';
import { HAND_LABELS } from '@/lib/labels';

export function RoundResultView() {
  const { state, send } = useGame();
  const { match, members, you, lastRoundResult, config, room } = state;

  if (!match || !config || !you || !room) return null;

  const isHost = you.is_host && you.player_id === room.host_player_id;
  const isSpectator = you.is_spectator;
  const showNext =
    isHost && config.round_advance_mode === 'MANUAL' && match.state === 'ROUND_RESULT';

  const nameById = new Map(members.map((m) => [m.player_id, m.display_name]));

  if (!lastRoundResult) {
    return (
      <div className="flex flex-col gap-4">
        {isSpectator ? <SpectatorBanner /> : null}
        <AliveRoster members={members} alivePlayerIds={match.alive_player_ids} />
        <Panel title="ラウンド結果">
          <div className="flex flex-col gap-4">
            <p className="text-center text-sm text-slate-300">
              再接続しました。詳細な手の結果は表示できませんが、ゲームは継続中です。
            </p>
            <p className="text-center text-xs text-slate-500">
              生存 {match.alive_player_ids.length} 人
            </p>
            {showNext ? (
              <PrimaryButton onClick={() => send('NEXT_ROUND')}>次のラウンドへ</PrimaryButton>
            ) : config.round_advance_mode === 'AUTO' ? (
              <p className="text-center text-xs text-slate-500">自動で次のラウンドに進みます…</p>
            ) : null}
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {isSpectator ? <SpectatorBanner /> : null}
      <RuleStatusBanner match={match} members={members} />
      <AliveRoster
        members={members}
        alivePlayerIds={match.alive_player_ids}
        bossPlayerId={match.boss_player_id ?? null}
        scores={match.scores}
      />

      <Panel
        title={`ラウンド ${lastRoundResult.round_no} の結果${
          lastRoundResult.segment_id ? ` · ${lastRoundResult.segment_id}` : ''
        }`}
      >
        <div className="flex flex-col gap-4">
          {lastRoundResult.is_draw ? (
            <p className="text-center text-lg font-semibold text-amber-300">あいこ！</p>
          ) : lastRoundResult.winner_ids.length > 0 ? (
            <p className="text-center text-lg font-semibold text-emerald-300">
              勝者: {lastRoundResult.winner_ids.map((id) => nameById.get(id) ?? id).join('、')}
            </p>
          ) : null}

          {Object.keys(lastRoundResult.scores).length > 0 ? (
            <ul className="text-sm text-slate-300">
              {Object.entries(lastRoundResult.scores).map(([id, score]) => (
                <li key={id} className="flex justify-between border-b border-slate-800 py-1">
                  <span>{nameById.get(id) ?? id}</span>
                  <span className="font-mono">{score} pt</span>
                </li>
              ))}
            </ul>
          ) : null}

          <ul className="flex flex-col gap-2">
            {Object.entries(lastRoundResult.hands).map(([playerId, hand]) => {
              const meta = HAND_LABELS[hand];
              const eliminated = lastRoundResult.eliminated_player_ids.includes(playerId);
              const isBoss = playerId === match.boss_player_id;
              return (
                <li
                  key={playerId}
                  className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
                    eliminated ? 'bg-rose-500/10 text-rose-200' : 'bg-slate-950/60 text-slate-200'
                  }`}
                >
                  <span>
                    {nameById.get(playerId) ?? playerId}
                    {isBoss ? ' · ボス' : ''}
                  </span>
                  <span>
                    {meta.emoji} {meta.label}
                    {eliminated ? ' · 脱落' : ''}
                  </span>
                </li>
              );
            })}
          </ul>

          <p className="text-center text-xs text-slate-500">
            生存 {lastRoundResult.alive_player_ids.length} 人
          </p>

          {showNext ? (
            <PrimaryButton onClick={() => send('NEXT_ROUND')}>次のラウンドへ</PrimaryButton>
          ) : config.round_advance_mode === 'AUTO' ? (
            <p className="text-center text-xs text-slate-500">自動で次のラウンドに進みます…</p>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}
