import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { CreateRoomModal } from '@/components/home/CreateRoomModal';
import { PrimaryButton, SecondaryButton } from '@/components/ui/Panel';
import { loadLastDisplayName } from '@/lib/displayNameStorage';
import { loadSession } from '@/lib/session';

export function HomePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [createOpen, setCreateOpen] = useState(false);
  const flash = (location.state as { message?: string } | null)?.message;

  const handleResume = () => {
    const session = loadSession();
    if (session) void navigate(`/rooms/${session.roomCode}`);
  };

  return (
    <section className="flex flex-col gap-6">
      <p className="text-sm leading-relaxed text-slate-300">
        みんなでブラウザから参加するリアルタイムじゃんけん。ルームを作るか、コードで参加してください。
      </p>

      {flash ? (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          {flash}
        </p>
      ) : null}

      <div className="flex flex-col gap-3">
        <PrimaryButton onClick={() => setCreateOpen(true)}>ルームを作成</PrimaryButton>
        <SecondaryButton onClick={() => void navigate('/join')}>コードで参加</SecondaryButton>
        {loadSession() ? (
          <SecondaryButton onClick={handleResume}>前回のルームに戻る</SecondaryButton>
        ) : null}
      </div>

      <CreateRoomModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        initialDisplayName={loadLastDisplayName()}
      />
    </section>
  );
}
