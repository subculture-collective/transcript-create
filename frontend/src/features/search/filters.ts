import type { ArchiveSearchFilters } from '../../types/api';

export type SearchFilters = ArchiveSearchFilters & { q: string };
const SORT_VALUES = new Set<NonNullable<ArchiveSearchFilters['sort_by']>>([
  'relevance',
  'date_asc',
  'date_desc',
  'duration_asc',
  'duration_desc',
]);
const MATCH_MODE_VALUES = new Set<NonNullable<ArchiveSearchFilters['match_mode']>>([
  'topic',
  'whole_word',
  'exact_phrase',
]);

function readMatchMode(value: string | null): NonNullable<ArchiveSearchFilters['match_mode']> {
  return value && MATCH_MODE_VALUES.has(value as NonNullable<ArchiveSearchFilters['match_mode']>)
    ? (value as NonNullable<ArchiveSearchFilters['match_mode']>)
    : 'topic';
}

function readSort(value: string | null): ArchiveSearchFilters['sort_by'] {
  return value && SORT_VALUES.has(value as NonNullable<ArchiveSearchFilters['sort_by']>)
    ? (value as NonNullable<ArchiveSearchFilters['sort_by']>)
    : undefined;
}

export function readFilters(params: URLSearchParams): SearchFilters {
  return {
    q: params.get('q') ?? '',
    match_mode: readMatchMode(params.get('match_mode')),
    date_from: params.get('date_from') ?? undefined,
    date_to: params.get('date_to') ?? undefined,
    sort_by: readSort(params.get('sort_by')),
    video_id: params.get('video_id') ?? undefined,
    limit: params.get('limit') ? Number(params.get('limit')) : undefined,
    offset: params.get('offset') ? Number(params.get('offset')) : undefined,
  };
}

export function serializeFilters(filters: SearchFilters) {
  const next = new URLSearchParams();
  if (filters.q.trim()) next.set('q', filters.q.trim());
  if (filters.match_mode && filters.match_mode !== 'topic')
    next.set('match_mode', filters.match_mode);
  if (filters.date_from) next.set('date_from', filters.date_from);
  if (filters.date_to) next.set('date_to', filters.date_to);
  if (filters.sort_by) next.set('sort_by', filters.sort_by);
  if (filters.video_id) next.set('video_id', filters.video_id);
  if (filters.limit != null && !Number.isNaN(filters.limit))
    next.set('limit', String(filters.limit));
  if (filters.offset != null && !Number.isNaN(filters.offset))
    next.set('offset', String(filters.offset));
  return next;
}

export function buildCurrentFilters(
  q: string,
  dateFrom: string,
  dateTo: string,
  sortBy: NonNullable<ArchiveSearchFilters['sort_by']>,
  existing: ArchiveSearchFilters & { video_id?: string; limit?: number; offset?: number }
) {
  return serializeFilters({
    q,
    match_mode: existing.match_mode,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    sort_by: sortBy,
    video_id: existing.video_id,
    limit: existing.limit,
    offset: existing.offset,
  });
}
