import useSWR, { type KeyedMutator } from 'swr';

import { ApiRequestError, getMatchHistory } from '@/lib/api';
import { MATCH_HISTORY_DEFAULT_LIMIT } from '@/lib/constants';
import type { MatchHistoryListResponse } from '@/types';

export interface UseMatchHistoryOptions {
  /** When false, skips fetching (e.g. outside lobby `WAITING`). Default true. */
  enabled?: boolean;
  /** Page size for `GET /rooms/{code}/matches` (default 20, max 50). */
  limit?: number;
}

export interface UseMatchHistoryResult {
  data: MatchHistoryListResponse | undefined;
  error: ApiRequestError | Error | undefined;
  isLoading: boolean;
  isValidating: boolean;
  /** Re-fetch history (manual refresh / after `RETURN_TO_LOBBY`). */
  refresh: () => Promise<MatchHistoryListResponse | undefined>;
  mutate: KeyedMutator<MatchHistoryListResponse>;
}

type MatchHistoryKey = readonly ['match-history', string, number];

function matchHistoryKey(
  roomCode: string | null | undefined,
  limit: number,
  enabled: boolean,
): MatchHistoryKey | null {
  if (!enabled || !roomCode) {
    return null;
  }
  return ['match-history', roomCode, limit] as const;
}

/**
 * SWR hook for room match history (`GET /rooms/{code}/matches`).
 *
 * Enable only in lobby (`WAITING`) so `MATCH_END` does not duplicate WS results.
 */
export function useMatchHistory(
  roomCode: string | null | undefined,
  options: UseMatchHistoryOptions = {},
): UseMatchHistoryResult {
  const { enabled = true, limit = MATCH_HISTORY_DEFAULT_LIMIT } = options;
  const key = matchHistoryKey(roomCode, limit, enabled);

  const { data, error, isLoading, isValidating, mutate } = useSWR<
    MatchHistoryListResponse,
    ApiRequestError | Error,
    MatchHistoryKey | null
  >(key, ([, code, lim]: MatchHistoryKey) => getMatchHistory(code, lim), {
    revalidateOnFocus: false,
    revalidateOnReconnect: true,
    revalidateOnMount: true,
  });

  const refresh = () => mutate();

  return {
    data,
    error,
    isLoading,
    isValidating,
    refresh,
    mutate,
  };
}
