import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { RoomScreen } from '@/components/room/RoomScreen';
import { GameProvider } from '@/context/GameContext';
import { useFatalSessionExit } from '@/hooks/useFatalSessionExit';
import { loadSession } from '@/lib/session';

function RoomSession() {
  useFatalSessionExit();
  return <RoomScreen />;
}

export function RoomPage() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const session = loadSession();

  useEffect(() => {
    if (!code) {
      void navigate('/', { replace: true });
      return;
    }
    if (!session || session.roomCode !== code) {
      void navigate(`/join/${code}`, { replace: true });
    }
  }, [code, session, navigate]);

  if (!code || !session || session.roomCode !== code) {
    return <p className="text-sm text-slate-400">読み込み中…</p>;
  }

  return (
    <GameProvider roomCode={session.roomCode} playerToken={session.playerToken}>
      <RoomSession />
    </GameProvider>
  );
}
