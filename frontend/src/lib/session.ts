/**
 * Player session persistence (ARCHITECTURE.md §3).
 *
 * `playerToken` is the sole proof of identity; keep it out of URLs and logs.
 */

export interface PlayerSession {
  roomCode: string;
  playerId: string;
  playerToken: string;
}

const STORAGE_KEY = 'rps.session';

export function loadSession(): PlayerSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      'roomCode' in parsed &&
      'playerId' in parsed &&
      'playerToken' in parsed &&
      typeof (parsed as PlayerSession).roomCode === 'string' &&
      typeof (parsed as PlayerSession).playerId === 'string' &&
      typeof (parsed as PlayerSession).playerToken === 'string'
    ) {
      return parsed as PlayerSession;
    }
    return null;
  } catch {
    return null;
  }
}

export function saveSession(session: PlayerSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(STORAGE_KEY);
}
