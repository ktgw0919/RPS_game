import type { MatchView, RoomView } from '@/types';

/** True while IN_GAME and not on the post-match result screen (SCREENS.md §5). */
export function isActiveMatch(room: RoomView, match: MatchView | null): boolean {
  return room.status === 'IN_GAME' && match !== null && match.state !== 'MATCH_END';
}

export function canMoveToAnotherRoom(room: RoomView, match: MatchView | null): boolean {
  return !isActiveMatch(room, match);
}

export const LEAVE_CONFIRM_LOBBY = 'ルームから退室してホームへ戻りますか？';

export const LEAVE_CONFIRM_ACTIVE_MATCH =
  '試合中に退室すると、マッチが終わるまでこのルームの定員を占有したままになります。退室しますか？';

export const SWITCH_ROOM_CONFIRM = 'いまのルームを離れ、別のルームに参加しますか？';

export const CREATE_ROOM_CONFIRM = 'いまのルームを離れ、新しいルームを作成しますか？';
