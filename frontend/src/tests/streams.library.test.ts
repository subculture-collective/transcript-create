import { describe, expect, it } from 'vitest';
import { dateFieldLabel, parseFilters, statusBadge } from '../features/streams/library';

describe('stream library helpers', () => {
  it('parses query filters and labels date fields', () => {
    const filters = parseFilters(new URLSearchParams({ q: 'vod', completed_only: 'true', date_field: 'created_at' }));

    expect(filters).toEqual({
      q: 'vod',
      completedOnly: true,
      dateField: 'created_at',
      dateFrom: '',
      dateTo: '',
      category: '',
    });
    expect(dateFieldLabel('created_at')).toBe('Created date');
  });

  it('maps stream states to badges', () => {
    expect(statusBadge({ state: 'ready', caption_ingest_state: 'done', diarization_state: 'done' } as never)).toMatchObject({ label: 'Ready' });
    expect(statusBadge({ state: 'queued' } as never)).toMatchObject({ label: 'Processing' });
  });
});
