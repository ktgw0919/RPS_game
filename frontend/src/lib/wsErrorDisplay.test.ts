import { describe, expect, it } from 'vitest';

import { formatWsError } from '@/lib/wsErrorDisplay';

describe('formatWsError', () => {
  it('translates ROOM_CLOSED server messages', () => {
    expect(formatWsError({ code: 'ROOM_CLOSED', message: 'Room has been closed.' })).toContain(
      '解散',
    );
  });

  it('translates START_CONDITION_UNMET detail', () => {
    expect(
      formatWsError({ code: 'START_CONDITION_UNMET', message: 'Not enough players to start.' }),
    ).toContain('人数');
  });

  it('falls back to code default when message is empty', () => {
    expect(formatWsError({ code: 'NOT_HOST', message: '' })).toContain('ホスト');
  });
});
