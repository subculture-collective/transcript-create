import { describe, expect, it } from 'vitest';
import { plainTextFromSnippet } from '../features/search/moments';

describe('search moment text', () => {
  it('preserves angle-bracket transcript text while removing paired legacy markers', () => {
    expect(plainTextFromSnippet('  Use <T> with <mark>rent</mark> and 5 < 7  ')).toBe(
      'Use <T> with rent and 5 < 7'
    );
  });

  it('preserves exact marker-shaped text for new plain-text payloads', () => {
    expect(plainTextFromSnippet('literal <mark>text</mark>', [])).toBe('literal <mark>text</mark>');
  });
});

import { bucketMomentsByDate } from '../components/archive/SearchInsights';

describe('bucketMomentsByDate', () => {
  const group = (uploaded_at: string | null, count: number) =>
    ({
      video: { id: uploaded_at ?? 'none', youtube_id: 'x', uploaded_at },
      moments: Array.from({ length: count }, (_, id) => ({
        id,
        video_id: 'v',
        start_ms: 0,
        end_ms: 1,
        snippet: '',
      })),
    }) as never;

  it('groups by year and keeps empty years between results', () => {
    expect(
      bucketMomentsByDate([
        group('2021-03-01T00:00:00Z', 2),
        group('2023-05-01T00:00:00Z', 1),
        group(null, 4),
      ])
    ).toEqual([
      { key: '2021', label: '2021', count: 2 },
      { key: '2022', label: '2022', count: 0 },
      { key: '2023', label: '2023', count: 1 },
    ]);
  });

  it('groups by month within a single year', () => {
    expect(
      bucketMomentsByDate([group('2026-01-10T00:00:00Z', 1), group('2026-03-02T00:00:00Z', 3)]).map(
        (bucket) => [bucket.label, bucket.count]
      )
    ).toEqual([
      ['Jan', 1],
      ['Feb', 0],
      ['Mar', 3],
    ]);
  });
});
