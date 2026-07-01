import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { PrimaryButton, SecondaryButton } from '@/components/ui/Panel';
import { joinRoom } from '@/lib/api';
import { DISPLAY_NAME_MAX_LEN, DISPLAY_NAME_MIN_LEN } from '@/lib/constants';
import { saveLastDisplayName } from '@/lib/displayNameStorage';
import { saveSession } from '@/lib/session';

interface JoinRoomFormProps {
  initialCode?: string;
  initialDisplayName?: string;
  /** When switching rooms, block joining the same code. */
  currentRoomCode?: string;
  beforeJoin?: () => Promise<void>;
  onJoined?: (roomCode: string) => void;
  onCancel?: () => void;
  submitLabel?: string;
}

export function JoinRoomForm({
  initialCode = '',
  initialDisplayName = 'Player',
  currentRoomCode,
  beforeJoin,
  onJoined,
  onCancel,
  submitLabel = '参加',
}: JoinRoomFormProps) {
  const navigate = useNavigate();
  const [code, setCode] = useState(initialCode);
  const [name, setName] = useState(initialDisplayName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmedCode = code.trim().toUpperCase();
    const trimmedName = name.trim();
    if (!trimmedCode) {
      setError('ルームコードを入力してください');
      return;
    }
    if (currentRoomCode && trimmedCode === currentRoomCode.trim().toUpperCase()) {
      setError('いまのルームと同じコードです');
      return;
    }
    if (trimmedName.length < DISPLAY_NAME_MIN_LEN || trimmedName.length > DISPLAY_NAME_MAX_LEN) {
      setError(`表示名は ${DISPLAY_NAME_MIN_LEN}〜${DISPLAY_NAME_MAX_LEN} 文字です`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (beforeJoin) await beforeJoin();
      const res = await joinRoom(trimmedCode, trimmedName);
      saveLastDisplayName(trimmedName);
      saveSession({
        roomCode: trimmedCode,
        playerId: res.player_id,
        playerToken: res.player_token,
      });
      if (onJoined) {
        onJoined(trimmedCode);
      } else {
        void navigate(`/rooms/${trimmedCode}`);
      }
    } catch (err) {
      if (err instanceof Error && err.message === 'cancelled') return;
      setError(err instanceof Error ? err.message : '参加に失敗しました');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-slate-400">ルームコード</span>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono uppercase tracking-widest text-slate-100"
          placeholder="ABCD"
          autoFocus={!initialCode}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-slate-400">表示名</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={DISPLAY_NAME_MAX_LEN}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
        />
      </label>
      {error ? <p className="text-sm text-amber-400">{error}</p> : null}
      <div className="flex gap-2">
        {onCancel ? <SecondaryButton onClick={onCancel}>キャンセル</SecondaryButton> : null}
        <PrimaryButton type="submit" disabled={busy} className="flex-1">
          {submitLabel}
        </PrimaryButton>
      </div>
    </form>
  );
}
