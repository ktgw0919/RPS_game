/** Last display name for join/create forms (SCREENS.md §5). */

const KEY = 'rps.lastDisplayName';

export function loadLastDisplayName(): string {
  try {
    return sessionStorage.getItem(KEY) ?? 'Player';
  } catch {
    return 'Player';
  }
}

export function saveLastDisplayName(name: string): void {
  try {
    sessionStorage.setItem(KEY, name);
  } catch {
    // ignore quota / private mode
  }
}
