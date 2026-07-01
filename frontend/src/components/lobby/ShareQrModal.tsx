import { useEffect } from 'react';

import QRCode from 'react-qr-code';

import { SecondaryButton } from '@/components/ui/Panel';

interface ShareQrModalProps {
  open: boolean;
  onClose: () => void;
  roomCode: string;
  joinUrl: string;
}

export function ShareQrModal({ open, onClose, roomCode, joinUrl }: ShareQrModalProps) {
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal
        aria-labelledby="share-qr-title"
        className="w-full max-w-sm rounded-2xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="share-qr-title" className="text-lg font-semibold text-white">
          参加用 QR コード
        </h2>
        <p className="mt-1 text-sm text-slate-400">
          スマートフォンで読み取ると参加画面（<span className="font-mono">{roomCode}</span>
          ）が開きます。
        </p>

        <div className="mt-4 flex justify-center rounded-xl bg-white p-4">
          <QRCode
            value={joinUrl}
            size={220}
            bgColor="#ffffff"
            fgColor="#000000"
            aria-label={`ルーム ${roomCode} の参加リンク QR コード`}
          />
        </div>

        <p className="mt-3 break-all text-center font-mono text-xs text-slate-500">{joinUrl}</p>

        <div className="mt-4">
          <SecondaryButton onClick={onClose} className="w-full">
            閉じる
          </SecondaryButton>
        </div>
      </div>
    </div>
  );
}
