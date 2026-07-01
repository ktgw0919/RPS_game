/**
 * User-facing WS / REST error text (ARCHITECTURE.md §4.1, SCREENS.md §5).
 *
 * Server `message` is auxiliary and often English; map known strings to Japanese
 * and fall back to code-specific defaults.
 */

import type { ErrorCode, ErrorPayload } from '@/types';

/** Known server English strings → Japanese (backend ws.py / rooms.py). */
const SERVER_MESSAGE_JA: Record<string, string> = {
  'Room has been closed.': 'ルームは解散しました（長時間無操作など）。',
  'Room closed.': 'ルームは解散しました（長時間無操作など）。',
  'Select a boss before starting.': 'ボスを選んでから開始してください。',
  'The nominated boss is not available.': '指名したボスが参加できません。',
  'Not enough players to start.': '開始に必要な人数が足りません。',
  'Start conditions are not met.': 'ゲームを開始する条件を満たしていません。',
  'Only the host can change settings.': 'ホストのみ設定を変更できます。',
  'Settings can only change in the lobby.': '設定はロビーでのみ変更できます。',
  'Settings out of the allowed range.': '設定値が許可範囲外です。',
  'Invalid settings payload.': '設定の送信内容が不正です。',
  'Only the host can add CPUs.': 'ホストのみ CPU を追加できます。',
  'CPU players are disabled.': 'この環境では CPU プレイヤーは利用できません。',
  'CPU players can only be added in the lobby.': 'CPU はロビーでのみ追加できます。',
  'Room is full.': 'ルームが満員です。',
  'Only the host can remove CPUs.': 'ホストのみ CPU を削除できます。',
  'CPU players can only be removed in the lobby.': 'CPU はロビーでのみ削除できます。',
  'No CPU player to remove.': '削除できる CPU がいません。',
  'Player is not a CPU.': 'そのプレイヤーは CPU ではありません。',
  'The game has already started.': 'ゲームはすでに開始されています。',
  'Only the host can advance the round.': 'ホストのみ次のラウンドへ進めます。',
  'Cannot advance the round right now.': '今は次のラウンドへ進めません。',
  'Only the host can return to the lobby.': 'ホストのみロビーへ戻れます。',
  'Can only return to lobby after the match ends.': 'マッチ終了後にのみロビーへ戻れます。',
  'Not accepting submissions right now.': '今は手を提出できません。',
  'Only alive players can submit a hand.': '生存者のみ手を提出できます。',
  Rejected: '操作を拒否されました。',
};

const CODE_DEFAULT_JA: Partial<Record<ErrorCode, string>> = {
  ROOM_CLOSED: 'ルームは解散しました（長時間無操作など）。',
  ROOM_NOT_FOUND: 'ルームが見つかりません。',
  START_CONDITION_UNMET: 'ゲームを開始する条件を満たしていません。',
  INVALID_STATE: '今はその操作はできません。',
  NOT_HOST: 'ホストのみ実行できる操作です。',
  CPU_NOT_ALLOWED: 'この環境では CPU プレイヤーは利用できません。',
  NOT_ALIVE: '生存していないため手を提出できません。',
  INVALID_PAYLOAD: '送信内容が不正です。',
  ROOM_FULL: 'ルームが満員です。',
};

/** Non-fatal errors that should appear in SessionNotices while the socket stays open. */
export const NON_FATAL_OPERATION_ERROR_CODES: ReadonlySet<ErrorCode> = new Set([
  'START_CONDITION_UNMET',
  'INVALID_STATE',
  'NOT_HOST',
  'INVALID_PAYLOAD',
  'CPU_NOT_ALLOWED',
  'NOT_ALIVE',
  'ROOM_FULL',
]);

export function formatWsError(payload: ErrorPayload): string {
  const translated = SERVER_MESSAGE_JA[payload.message];
  if (translated) return translated;
  if (payload.message.trim()) return payload.message;
  return CODE_DEFAULT_JA[payload.code] ?? payload.code;
}
