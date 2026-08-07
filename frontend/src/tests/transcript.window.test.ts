import { describe, expect, it } from 'vitest';
import { ensureIndexVisible, windowAroundIndex } from '../features/videoTranscript/window';

describe('transcript reading windows', () => {
  it('centers a bounded window on a cited moment in a long transcript', () => {
    expect(windowAroundIndex(1_000, 640, 80)).toEqual({ start: 600, end: 680 });
  });

  it('clamps windows at transcript boundaries', () => {
    expect(windowAroundIndex(45, 0, 80)).toEqual({ start: 0, end: 45 });
    expect(windowAroundIndex(1_000, 999, 80)).toEqual({ start: 920, end: 1_000 });
  });

  it('moves only when the active moment leaves the mounted range', () => {
    const current = { start: 600, end: 680 };
    expect(ensureIndexVisible(1_000, 650, current, 80)).toEqual(current);
    expect(ensureIndexVisible(1_000, 700, current, 80)).toEqual({ start: 660, end: 740 });
  });
});
