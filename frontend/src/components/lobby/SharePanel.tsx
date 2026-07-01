import { useState } from 'react';

import { ShareQrModal } from '@/components/lobby/ShareQrModal';
import { SecondaryButton } from '@/components/ui/Panel';

interface SharePanelProps {
  roomCode: string;
}

export function SharePanel({ roomCode }: SharePanelProps) {
  const [copied, setCopied] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const joinUrl = `${window.location.origin}/join/${roomCode}`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(roomCode);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt('ルームコードをコピーしてください', roomCode);
    }
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(joinUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt('参加リンクをコピーしてください', joinUrl);
    }
  };

  return (
    <>
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs text-slate-500">ルームコード</p>
            <p className="font-mono text-2xl font-bold tracking-widest text-white">{roomCode}</p>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <SecondaryButton onClick={() => setQrOpen(true)}>QR</SecondaryButton>
            <SecondaryButton onClick={() => void handleCopy()}>
              {copied ? 'コピー済' : 'コード'}
            </SecondaryButton>
            <SecondaryButton onClick={() => void handleCopyLink()}>リンク</SecondaryButton>
          </div>
        </div>
        <p className="text-xs text-slate-500">
          友だちに QR・コード・リンクを共有して参加してもらいましょう。
        </p>
      </div>

      <ShareQrModal
        open={qrOpen}
        onClose={() => setQrOpen(false)}
        roomCode={roomCode}
        joinUrl={joinUrl}
      />
    </>
  );
}
