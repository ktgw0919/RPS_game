import { describe, expect, it } from 'vitest';

import { gameReducer, initialGameState, type GameState } from '@/reducers/gameReducer';
import { DEFAULT_MATCH_CONFIG, type MatchConfig, type PlayerView, type RoomView } from '@/types';

const SERVER_NOW = '2026-06-29T08:00:00.000Z';
const DEADLINE = '2026-06-29T08:00:10.000Z';

function player(id: string, overrides: Partial<PlayerView> = {}): PlayerView {
  return {
    player_id: id,
    display_name: id,
    is_host: id === 'p1',
    connection_state: 'CONNECTED',
    is_spectator: false,
    is_cpu: false,
    ...overrides,
  };
}

function room(overrides: Partial<RoomView> = {}): RoomView {
  return {
    room_code: 'ABCD',
    status: 'WAITING',
    host_player_id: 'p1',
    member_count: 2,
    capacity: 20,
    config: DEFAULT_MATCH_CONFIG,
    ...overrides,
  };
}

function lobbyState(overrides: Partial<GameState> = {}): GameState {
  return {
    ...initialGameState,
    room: room(),
    config: DEFAULT_MATCH_CONFIG,
    members: [player('p1'), player('p2')],
    you: player('p1'),
    connectionStatus: 'connected',
    ...overrides,
  };
}

describe('gameReducer', () => {
  it('applies first ROUND_START when match is still null (post START_GAME bootstrap)', () => {
    const state = lobbyState({ match: null });

    const next = gameReducer(state, {
      type: 'ROUND_START',
      payload: {
        round_no: 1,
        deadline_at: DEADLINE,
        server_now: SERVER_NOW,
        alive_player_ids: ['p1', 'p2'],
        segment_id: null,
      },
    });

    expect(next.match).not.toBeNull();
    expect(next.match?.state).toBe('COLLECTING');
    expect(next.match?.current_round_no).toBe(1);
    expect(next.match?.rule_type).toBe('NORMAL');
    expect(next.room?.status).toBe('IN_GAME');
    expect(next.roundTiming?.round_no).toBe(1);
    expect(next.lastRoundResult).toBeNull();
  });

  it('bootstraps TOURNAMENT ROUND_START when match is null (segment_id regression)', () => {
    const tournamentConfig: MatchConfig = {
      ...DEFAULT_MATCH_CONFIG,
      rule_type: 'TOURNAMENT',
    };
    const state = lobbyState({
      room: room({ config: tournamentConfig, status: 'WAITING' }),
      config: tournamentConfig,
      match: null,
    });

    const next = gameReducer(state, {
      type: 'ROUND_START',
      payload: {
        round_no: 1,
        deadline_at: DEADLINE,
        server_now: SERVER_NOW,
        alive_player_ids: ['p1', 'p2'],
        segment_id: 'pair-1',
      },
    });

    expect(next.match?.rule_type).toBe('TOURNAMENT');
    expect(next.match?.segment_id).toBe('pair-1');
    expect(next.roundTiming?.segment_id).toBe('pair-1');
  });

  it('ignores TOURNAMENT ROUND_START for another pair when match already exists', () => {
    const tournamentConfig: MatchConfig = {
      ...DEFAULT_MATCH_CONFIG,
      rule_type: 'TOURNAMENT',
    };
    const state = lobbyState({
      room: room({ config: tournamentConfig, status: 'IN_GAME' }),
      config: tournamentConfig,
      match: {
        match_id: 'm1',
        rule_type: 'TOURNAMENT',
        state: 'COLLECTING',
        current_round_no: 1,
        alive_player_ids: ['p1', 'p2'],
        scores: {},
        deadline_at: DEADLINE,
        my_submitted: false,
        segment_id: 'pair-1',
      },
      roundTiming: {
        round_no: 1,
        deadline_at: DEADLINE,
        server_now: SERVER_NOW,
        alive_player_ids: ['p1', 'p2'],
        segment_id: 'pair-1',
      },
    });

    const next = gameReducer(state, {
      type: 'ROUND_START',
      payload: {
        round_no: 2,
        deadline_at: '2026-06-29T08:00:20.000Z',
        server_now: '2026-06-29T08:00:11.000Z',
        alive_player_ids: ['p3', 'p4'],
        segment_id: 'pair-2',
      },
    });

    expect(next).toBe(state);
    expect(next.match?.segment_id).toBe('pair-1');
    expect(next.roundTiming?.segment_id).toBe('pair-1');
  });

  it('clears match state on LOBBY_UPDATE after MATCH_END (return to lobby)', () => {
    const state = lobbyState({
      room: room({ status: 'IN_GAME' }),
      match: {
        match_id: 'm1',
        rule_type: 'NORMAL',
        state: 'MATCH_END',
        current_round_no: 3,
        alive_player_ids: ['p1'],
        scores: {},
        deadline_at: null,
        my_submitted: false,
      },
      lastMatchEnd: {
        match_id: 'm1',
        winner_ids: ['p1'],
        scores: {},
        reason: 'DECIDED',
      },
      lastRoundResult: {
        round_no: 3,
        hands: { p1: 'ROCK', p2: 'SCISSORS' },
        is_draw: false,
        winner_ids: ['p1'],
        eliminated_player_ids: ['p2'],
        alive_player_ids: ['p1'],
        scores: {},
        segment_id: null,
      },
      roundTiming: {
        round_no: 3,
        deadline_at: DEADLINE,
        server_now: SERVER_NOW,
        alive_player_ids: ['p1', 'p2'],
        segment_id: null,
      },
      submissionProgress: {
        round_no: 3,
        submitted_player_ids: ['p1', 'p2'],
        expected_count: 2,
        segment_id: null,
      },
      serverNow: SERVER_NOW,
    });

    const next = gameReducer(state, {
      type: 'LOBBY_UPDATE',
      payload: {
        members: [player('p1'), player('p2')],
        host_player_id: 'p1',
        config: DEFAULT_MATCH_CONFIG,
      },
    });

    expect(next.room?.status).toBe('WAITING');
    expect(next.match).toBeNull();
    expect(next.lastMatchEnd).toBeNull();
    expect(next.lastRoundResult).toBeNull();
    expect(next.roundTiming).toBeNull();
    expect(next.submissionProgress).toBeNull();
  });
});
