import { describe, expect, it } from 'vitest';
import {
  buildPassageLink,
  formatPassageTime,
  parsePassageTime,
  passageRangeError,
  readPassageRange,
} from '../features/passages/range';

describe('passage URLs and times', () => {
  it('round trips a precise range without changing old timestamp conventions', () => {
    const range = { startMs: 1108670, endMs: 1120530 };
    const url = new URL(buildPassageLink('video-1', range), 'https://archive.test');
    expect(url.pathname).toBe('/v/video-1');
    expect(url.hash).toBe('#moment-1108670');
    expect(readPassageRange(url.searchParams)).toEqual(range);
    expect(readPassageRange(new URLSearchParams('t=12'))).toBeNull();
    expect(parsePassageTime(formatPassageTime(range.startMs))).toBe(range.startMs);
    expect(parsePassageTime('12.125')).toBe(12125);
    expect(parsePassageTime('01:02:03.004')).toBe(3723004);
  });

  it.each(['', '-2', 'Infinity', '1e3', '12:99', '1:2', '00:01:60', '0.0001'])(
    'rejects malformed input %s',
    (value) => {
      expect(parsePassageTime(value)).toBeNull();
    }
  );

  it('rejects malformed URLs, reversed ranges, and times outside the recording', () => {
    for (const query of [
      'end_ms=20',
      't=NaN&end_ms=30',
      't_ms=1.5&end_ms=30',
      't=1&end_ms=',
      't=1&end_ms=Infinity',
      't=1&end_ms=2',
    ]) {
      const range = readPassageRange(new URLSearchParams(query))!;
      expect(passageRangeError(range.startMs, range.endMs)).toBeTruthy();
    }
    expect(passageRangeError(0, 2000, 1000)).toMatch(/within/);
    expect(passageRangeError(1000, 1000)).toMatch(/after/);
    expect(passageRangeError(0, 1000, 1000)).toBeNull();
  });
});
