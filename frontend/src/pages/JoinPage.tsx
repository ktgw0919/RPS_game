import { useNavigate, useParams } from 'react-router-dom';

import { JoinRoomForm } from '@/components/home/JoinRoomForm';
import { loadLastDisplayName } from '@/lib/displayNameStorage';

export function JoinPage() {
  const { code } = useParams<{ code?: string }>();
  const navigate = useNavigate();

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-white">ルームに参加</h2>
      <JoinRoomForm
        initialCode={code ?? ''}
        initialDisplayName={loadLastDisplayName()}
        onCancel={() => void navigate('/')}
      />
    </section>
  );
}
