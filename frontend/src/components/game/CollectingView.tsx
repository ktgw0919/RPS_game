import { useEffect, useMemo, useState } from 'react';

import { AliveRoster } from '@/components/game/AliveRoster';
import { DeadlineTimer } from '@/components/game/DeadlineTimer';
import { HandPicker } from '@/components/game/HandPicker';
import { SpectatorBanner } from '@/components/game/SpectatorBanner';
import { Panel } from '@/components/ui/Panel';
import { useDeadline } from '@/hooks/useDeadline';
import { useGame } from '@/hooks/useGame';
import { deriveRoundTiming } from '@/lib/gameView';
import type { Hand } from '@/types';

export function CollectingView() {
  const { state, send } = useGame();
  const { match, you, roundTiming, submissionProgress, serverNow, members, connectionStatus } =
    state;
  const [picked, setPicked] = useState<Hand | null>(null);

  const timing = useMemo(
    () => roundTiming ?? deriveRoundTiming(match, serverNow),
    [roundTiming, match, serverNow],
  );

  useEffect(() => {
    setPicked(null);
  }, [timing?.round_no]);

  const msLeft = useDeadline(timing?.server_now ?? serverNow, timing?.deadline_at ?? null);
  const deadlinePassed = msLeft !== null && msLeft <= 0;

  if (!match || !you || !timing) return null;

  const isOnline = connectionStatus === 'connected';
  const isSpectator = you.is_spectator;
  const isAlive = match.alive_player_ids.includes(you.player_id);
  const canSubmit = isOnline && isAlive && !isSpectator && !match.my_submitted && !deadlinePassed;

  const submitted = submissionProgress?.submitted_player_ids.length ?? null;
  const expected = submissionProgress?.expected_count ?? match.alive_player_ids.length;
  const allSubmitted =
    submitted !== null ? submitted >= expected && expected > 0 : match.my_submitted;
  const judging = match.my_submitted && (allSubmitted || deadlinePassed);

  const handlePick = (hand: Hand) => {
    if (!canSubmit) return;
    setPicked(hand);
    send('SUBMIT_HAND', { round_no: timing.round_no, hand });
  };

  return (
    <div className="flex flex-col gap-4">
      {isSpectator ? <SpectatorBanner /> : null}

      {!isOnline ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          接続が切れています。再接続が完了するまで手札を選べません。
        </div>
      ) : null}

      <AliveRoster members={members} alivePlayerIds={match.alive_player_ids} />

      <Panel title={`ラウンド ${timing.round_no}`}>
        <div className="flex flex-col gap-4">
          <DeadlineTimer serverNow={timing.server_now} deadlineAt={timing.deadline_at} />

          {deadlinePassed && !judging ? (
            <p className="text-center text-sm text-amber-300">
              締切を過ぎました。未提出のプレイヤーは敗北扱いになります…
            </p>
          ) : null}

          <p className="text-center text-sm text-slate-400">
            提出 {submitted !== null ? `${submitted}/${expected}` : `—/${expected}`}
          </p>

          {judging ? (
            <p className="text-center text-sm text-indigo-300">判定中…</p>
          ) : isSpectator || !isAlive ? (
            <p className="text-center text-sm text-slate-400">プレイヤーの手札提出を待っています</p>
          ) : match.my_submitted ? (
            <p className="text-center text-sm text-emerald-400">
              提出済み — 他のプレイヤーを待っています
            </p>
          ) : deadlinePassed ? (
            <p className="text-center text-sm text-slate-400">提出受付は終了しました</p>
          ) : (
            <>
              <p className="text-center text-sm text-slate-300">手札を選んでください</p>
              <HandPicker disabled={!canSubmit} selected={picked} onPick={handlePick} />
            </>
          )}
        </div>
      </Panel>
    </div>
  );
}
