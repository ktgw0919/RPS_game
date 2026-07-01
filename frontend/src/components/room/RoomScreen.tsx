import { ConnectionBanner } from '@/components/room/ConnectionBanner';
import { SessionNotices } from '@/components/room/SessionNotices';
import { GameScreen } from '@/components/game/GameScreen';
import { LobbyScreen } from '@/components/lobby/LobbyScreen';
import { useGame } from '@/hooks/useGame';

export function RoomScreen() {
  const { state } = useGame();
  const { room, match } = state;

  const inLobby = room?.status === 'WAITING' || !match;

  return (
    <div className="flex flex-col gap-4">
      <ConnectionBanner />
      <SessionNotices />
      {inLobby ? <LobbyScreen /> : <GameScreen />}
    </div>
  );
}
