import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { CreateRoomModal } from '@/components/home/CreateRoomModal';
import { JoinRoomForm } from '@/components/home/JoinRoomForm';
import { Panel, SecondaryButton } from '@/components/ui/Panel';
import { useExitRoom } from '@/hooks/useExitRoom';
import { useGame } from '@/hooks/useGame';
import { loadLastDisplayName } from '@/lib/displayNameStorage';
import {
  canMoveToAnotherRoom,
  CREATE_ROOM_CONFIRM,
  isActiveMatch,
  LEAVE_CONFIRM_ACTIVE_MATCH,
  LEAVE_CONFIRM_LOBBY,
  SWITCH_ROOM_CONFIRM,
} from '@/lib/roomActions';

export function RoomActionsPanel() {
  const { state, reset } = useGame();
  const { exitCurrentRoom } = useExitRoom();
  const navigate = useNavigate();
  const { room, match, you } = state;

  const [expanded, setExpanded] = useState(false);
  const [showSwitchForm, setShowSwitchForm] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  if (!room) return null;

  const roomCode = room.room_code;
  const activeMatch = isActiveMatch(room, match);
  const canMove = canMoveToAnotherRoom(room, match);
  const defaultName = you?.display_name ?? loadLastDisplayName();

  const handleLeaveHome = () => {
    const ok = window.confirm(activeMatch ? LEAVE_CONFIRM_ACTIVE_MATCH : LEAVE_CONFIRM_LOBBY);
    if (!ok) return;
    void (async () => {
      await exitCurrentRoom();
      reset();
      void navigate('/', { replace: true });
    })();
  };

  const handleOpenCreate = () => {
    if (!canMove) return;
    setCreateOpen(true);
  };

  const handleBeforeMove = async () => {
    if (!window.confirm(SWITCH_ROOM_CONFIRM)) {
      throw new Error('cancelled');
    }
    await exitCurrentRoom();
    reset();
  };

  const handleBeforeCreate = async () => {
    if (!window.confirm(CREATE_ROOM_CONFIRM)) {
      throw new Error('cancelled');
    }
    await exitCurrentRoom();
    reset();
  };

  const handleJoined = (newCode: string) => {
    setShowSwitchForm(false);
    setExpanded(false);
    void navigate(`/rooms/${newCode}`, { replace: true });
  };

  const handleCreated = (newCode: string) => {
    setCreateOpen(false);
    setExpanded(false);
    void navigate(`/rooms/${newCode}`, { replace: true });
  };

  return (
    <>
      <Panel>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-center justify-between text-left text-sm font-semibold text-slate-200"
          aria-expanded={expanded}
        >
          <span>ルーム操作</span>
          <span className="text-slate-500" aria-hidden>
            {expanded ? '▲' : '▼'}
          </span>
        </button>

        {expanded ? (
          <div className="mt-4 flex flex-col gap-3 border-t border-slate-800 pt-4">
            <p className="text-sm text-slate-400">
              いま:{' '}
              <span className="font-mono font-semibold tracking-widest text-slate-100">
                {roomCode}
              </span>
            </p>

            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <SecondaryButton
                disabled={!canMove}
                onClick={() => setShowSwitchForm((v) => !v)}
                className="flex-1 sm:flex-none"
              >
                別のルームへ
              </SecondaryButton>
              <SecondaryButton
                disabled={!canMove}
                onClick={handleOpenCreate}
                className="flex-1 sm:flex-none"
              >
                新しいルーム
              </SecondaryButton>
            </div>

            {!canMove ? (
              <p className="text-xs text-amber-200/90">
                マッチ進行中は別ルームへ移動できません。マッチ終了後にお試しください。
              </p>
            ) : null}

            {showSwitchForm && canMove ? (
              <JoinRoomForm
                initialDisplayName={defaultName}
                currentRoomCode={roomCode}
                beforeJoin={handleBeforeMove}
                onJoined={handleJoined}
                onCancel={() => setShowSwitchForm(false)}
                submitLabel="移動する"
              />
            ) : null}

            <SecondaryButton onClick={handleLeaveHome}>退室（ホームへ）</SecondaryButton>
          </div>
        ) : null}
      </Panel>

      <CreateRoomModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        initialDisplayName={defaultName}
        beforeCreate={handleBeforeCreate}
        onCreated={handleCreated}
      />
    </>
  );
}
