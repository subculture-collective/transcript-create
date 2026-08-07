import { describe, expect, it } from 'vitest';
import { buildTimestampLink, formatVideoTitle } from '../features/archive/format';

describe('archive moment links', () => {
  it('uses the transcript source and start time as the canonical rendered anchor', () => {
    expect(buildTimestampLink('video-1', 5_956_000, 'whisper')).toBe(
      '/v/video-1?t=5956&source=whisper#moment-whisper-5956000'
    );
  });

  it('uses an intentional date treatment for missing or dangling titles', () => {
    expect(formatVideoTitle('HasanAbi broadcast —', '2026-08-07T00:00:00Z')).toBe(
      'HasanAbi broadcast'
    );
    expect(formatVideoTitle('', '2026-08-07T00:00:00Z')).toMatch(/^Broadcast from /);
  });
});
