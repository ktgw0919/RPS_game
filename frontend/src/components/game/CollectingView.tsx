import { useEffect, useMemo, useState } from 'react';

import { AliveRoster } from '@/components/game/AliveRoster';
import { DeadlineTimer } from '@/components/game/DeadlineTimer';
import { HandPicker } from '@/components/game/HandPicker';
import { RuleStatusBanner } from '@/components/game/RuleStatusBanner';
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
  }, [timing?.round_no, timing?.segment_id]);

  const msLeft = useDeadline(timing?.server_now ?? serverNow, timing?.deadline_at ?? null);
  const deadlinePassed = msLeft !== null && msLeft <= 0;

  if (!match || !you) return null;

  const isTournament = match.rule_type === 'TOURNAMENT';
  const waitingOtherPair = isTournament && !timing && match.state === 'COLLECTING';

  if (!timing && !waitingOtherPair) return null;

  const isOnline = connectionStatus === 'connected';
  const isSpectator = you.is_spectator;
  const pairAliveIds = timing?.alive_player_ids ?? [];
  const isInPair = pairAliveIds.includes(you.player_id);
  const isAlive =
    match.rule_type === 'TOURNAMENT' ? isInPair : match.alive_player_ids.includes(you.player_id);
  const canSubmit =
    isOnline && isAlive && !isSpectator && !match.my_submitted && !deadlinePassed && timing != null;

  const submitted = submissionProgress?.submitted_player_ids.length ?? null;
  const expected =
    submissionProgress?.expected_count ??
    (isTournament ? pairAliveIds.length : match.alive_player_ids.length);
  const allSubmitted =
    submitted !== null ? submitted >= expected && expected > 0 : match.my_submitted;
  const judging = match.my_submitted && (allSubmitted || deadlinePassed);

  const handlePick = (hand: Hand) => {
    if (!canSubmit || !timing) return;
    setPicked(hand);
    const payload: { round_no: number; hand: Hand; segment_id?: string } = {
      round_no: timing.round_no,
      hand,
    };
    if (isTournament && timing.segment_id) {
      payload.segment_id = timing.segment_id;
    }
    send('SUBMIT_HAND', payload);
  };

  const panelTitle = timing
    ? `ラウンド ${timing.round_no}${timing.segment_id ? ` · ${timing.segment_id}` : ''}`
    : 'トーナメント';

  return (
    <div className="flex flex-col gap-4">
      {isSpectator ? <SpectatorBanner /> : null}
      <RuleStatusBanner match={match} members={members} />

      {!isOnline ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          接続が切れています。再接続が完了するまで手札を選べません。
        </div>
      ) : null}

      <AliveRoster
        members={members}
        alivePlayerIds={isTournament ? pairAliveIds : match.alive_player_ids}
        bossPlayerId={match.boss_player_id ?? null}
        scores={match.scores}
      />

      <Panel title={panelTitle}>
        <div className="flex flex-col gap-4">
          {timing ? (
            <DeadlineTimer serverNow={timing.server_now} deadlineAt={timing.deadline_at} />
          ) : null}

          {waitingOtherPair ? (
            <p className="text-center text-sm text-slate-400">
              他のペアの対戦中です。あなたのペアのラウンド開始を待っています…
            </p>
          ) : null}

          {timing && deadlinePassed && !judging ? (
            <p className="text-center text-sm text-amber-300">
              締切を過ぎました。未提出のプレイヤーは敗北扱いになります…
            </p>
          ) : null}

          {timing ? (
            <p className="text-center text-sm text-slate-400">
              提出 {submitted !== null ? `${submitted}/${expected}` : `—/${expected}`}
            </p>
          ) : null}

          {judging ? (
            <p className="text-center text-sm text-indigo-300">判定中…</p>
          ) : waitingOtherPair ? null : isSpectator || !isAlive ? (
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
