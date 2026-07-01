import { useState } from 'react';

import { Divider, Panel, PrimaryButton } from '@/components/ui/Panel';
import { MatchHistoryPanel } from '@/components/lobby/MatchHistoryPanel';
import { MemberList } from '@/components/lobby/MemberList';
import { SettingsPanel } from '@/components/lobby/SettingsPanel';
import { SharePanel } from '@/components/lobby/SharePanel';
import { useAllowCpu } from '@/hooks/useAllowCpu';
import { useGame } from '@/hooks/useGame';
import {
  canStartGame,
  eligiblePlayerIds,
  getStartBlockReason,
  minPlayersFor,
} from '@/lib/matchConfig';

export function LobbyScreen() {
  const { state, send } = useGame();
  const { room, members, you, config, connectionStatus } = state;
  const allowCpu = useAllowCpu();
  const [addCpuBusy, setAddCpuBusy] = useState(false);

  if (!room || !config || !you) return null;

  const isHost = you.is_host && you.player_id === room.host_player_id;
  const isConnected = connectionStatus === 'connected';
  const startBlocked = getStartBlockReason(members, config);
  const canStart = isHost && isConnected && canStartGame(members, config);
  const hostMember = members.find((m) => m.player_id === room.host_player_id);
  const hostDisconnected = hostMember?.connection_state === 'DISCONNECTED' && !hostMember.is_cpu;
  const roomFull = members.length >= room.capacity;
  const cpuControlsEnabled = isHost && allowCpu === true && room.status === 'WAITING';
  const eligible = eligiblePlayerIds(members);
  const needsCpuHint =
    isHost &&
    allowCpu === true &&
    !canStart &&
    eligible.length < minPlayersFor(config.rule_type) &&
    eligible.length >= 1;

  const handleAddCpu = () => {
    setAddCpuBusy(true);
    send('ADD_CPU', { count: 1 });
    window.setTimeout(() => setAddCpuBusy(false), 400);
  };

  const handleRemoveCpu = (playerId: string) => {
    send('REMOVE_CPU', { player_id: playerId });
  };

  return (
    <div className="flex flex-col gap-4">
      {hostDisconnected ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          ホストが切断中です。復帰しない場合、しばらくすると別のプレイヤーにホストが移譲されます。
        </div>
      ) : null}
      <Panel>
        <SharePanel roomCode={room.room_code} />
      </Panel>

      <Divider />

      <MatchHistoryPanel roomCode={room.room_code} />

      <Divider />

      <Panel>
        <MemberList
          members={members}
          capacity={room.capacity}
          hostPlayerId={room.host_player_id}
          cpuControlsEnabled={cpuControlsEnabled}
          roomFull={roomFull}
          onAddCpu={handleAddCpu}
          onRemoveCpu={handleRemoveCpu}
          addCpuBusy={addCpuBusy}
        />
      </Panel>

      <Divider />

      <Panel title="ゲーム設定">
        <SettingsPanel config={config} editable={isHost} members={members} />
      </Panel>

      <Divider />

      {isHost ? (
        <div className="flex flex-col gap-2">
          <PrimaryButton disabled={!canStart} onClick={() => send('START_GAME')}>
            ゲーム開始
          </PrimaryButton>
          {startBlocked ? (
            <p className="text-center text-xs text-amber-400">{startBlocked}</p>
          ) : !isConnected ? (
            <p className="text-center text-xs text-amber-400">
              サーバーに接続中です。接続が完了してから開始できます。
            </p>
          ) : null}
          {needsCpuHint ? (
            <p className="text-center text-xs text-slate-500">
              デモ用に「＋CPUを追加」すると1人でもゲームを開始できます
            </p>
          ) : null}
        </div>
      ) : (
        <p className="text-center text-sm text-slate-400">ホストの開始を待っています…</p>
      )}
    </div>
  );
}
