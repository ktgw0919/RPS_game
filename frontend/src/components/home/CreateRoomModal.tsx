import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PrimaryButton, SecondaryButton } from '@/components/ui/Panel';
import { createRoom } from '@/lib/api';
import { DISPLAY_NAME_MAX_LEN, DISPLAY_NAME_MIN_LEN } from '@/lib/constants';
import { saveSession } from '@/lib/session';

interface CreateRoomModalProps {
  open: boolean;
  onClose: () => void;
}

export function CreateRoomModal({ open, onClose }: CreateRoomModalProps) {
  const navigate = useNavigate();
  const [name, setName] = useState('Player');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed.length < DISPLAY_NAME_MIN_LEN || trimmed.length > DISPLAY_NAME_MAX_LEN) {
      setError(`表示名は ${DISPLAY_NAME_MIN_LEN}〜${DISPLAY_NAME_MAX_LEN} 文字です`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await createRoom(trimmed);
      saveSession({
        roomCode: res.room_code,
        playerId: res.player_id,
        playerToken: res.player_token,
      });
      onClose();
      void navigate(`/rooms/${res.room_code}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ルーム作成に失敗しました');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal
        aria-labelledby="create-room-title"
        className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="create-room-title" className="text-lg font-semibold text-white">
          ルームを作成
        </h2>
        <form onSubmit={(e) => void handleSubmit(e)} className="mt-4 flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-slate-400">表示名</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={DISPLAY_NAME_MAX_LEN}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
              autoFocus
            />
          </label>
          {error ? <p className="text-sm text-amber-400">{error}</p> : null}
          <div className="flex gap-2">
            <SecondaryButton onClick={onClose}>キャンセル</SecondaryButton>
            <PrimaryButton type="submit" disabled={busy} className="flex-1">
              作成
            </PrimaryButton>
          </div>
        </form>
      </div>
    </div>
  );
}
