import { describe, expect, it } from 'vitest';
import { buildCurrentFilters, readFilters, serializeFilters } from '../features/search/filters';

describe('search filters helpers', () => {
  it('reads and serializes archive filters', () => {
    const params = new URLSearchParams({
      q: 'hasan',
      source: 'native',
      category: 'news',
      date_from: '2026-05-01',
      min_duration: '120',
      limit: '25',
    });

    expect(readFilters(params)).toEqual({
      q: 'hasan',
      source: 'native',
      category: 'news',
      date_from: '2026-05-01',
      date_to: undefined,
      min_duration: 120,
      max_duration: undefined,
      sort_by: undefined,
      video_id: undefined,
      limit: 25,
      offset: undefined,
    });

    expect(
      serializeFilters({
        q: 'hasan',
        source: 'native',
        category: 'news',
        date_from: '2026-05-01',
        date_to: undefined,
        min_duration: 120,
        max_duration: undefined,
        sort_by: 'relevance',
        video_id: undefined,
        limit: 25,
        offset: 50,
      }).toString()
    ).toBe('q=hasan&source=native&category=news&date_from=2026-05-01&min_duration=120&sort_by=relevance&limit=25&offset=50');
  });

  it('builds save-search filters without stale blanks', () => {
    expect(
      buildCurrentFilters('topic', undefined, '', '', '', '', '', 'relevance', {
        video_id: 'video-1',
        limit: 25,
        offset: 50,
      }).toString()
    ).toBe('q=topic&sort_by=relevance&video_id=video-1&limit=25&offset=50');
  });
});
