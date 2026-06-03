import type { ArchiveSearchFilters } from '../../types/api';

export type SearchFilters = ArchiveSearchFilters & { q: string };

export function readFilters(params: URLSearchParams): SearchFilters {
  return {
    q: params.get('q') ?? '',
    source: (params.get('source') as ArchiveSearchFilters['source']) ?? undefined,
    category: params.get('category') ?? undefined,
    date_from: params.get('date_from') ?? undefined,
    date_to: params.get('date_to') ?? undefined,
    min_duration: params.get('min_duration') ? Number(params.get('min_duration')) : undefined,
    max_duration: params.get('max_duration') ? Number(params.get('max_duration')) : undefined,
    sort_by: params.get('sort_by') ?? undefined,
    video_id: params.get('video_id') ?? undefined,
    limit: params.get('limit') ? Number(params.get('limit')) : undefined,
    offset: params.get('offset') ? Number(params.get('offset')) : undefined,
  };
}

export function serializeFilters(filters: SearchFilters) {
  const next = new URLSearchParams();
  if (filters.q.trim()) next.set('q', filters.q.trim());
  if (filters.source) next.set('source', filters.source);
  if (filters.category) next.set('category', filters.category);
  if (filters.date_from) next.set('date_from', filters.date_from);
  if (filters.date_to) next.set('date_to', filters.date_to);
  if (filters.min_duration != null && !Number.isNaN(filters.min_duration)) next.set('min_duration', String(filters.min_duration));
  if (filters.max_duration != null && !Number.isNaN(filters.max_duration)) next.set('max_duration', String(filters.max_duration));
  if (filters.sort_by) next.set('sort_by', filters.sort_by);
  if (filters.video_id) next.set('video_id', filters.video_id);
  if (filters.limit != null && !Number.isNaN(filters.limit)) next.set('limit', String(filters.limit));
  if (filters.offset != null && !Number.isNaN(filters.offset)) next.set('offset', String(filters.offset));
  return next;
}

export function buildCurrentFilters(
  q: string,
  source: ArchiveSearchFilters['source'],
  dateFrom: string,
  dateTo: string,
  category: string,
  minDuration: string,
  maxDuration: string,
  sortBy: string,
  existing: ArchiveSearchFilters & { video_id?: string; limit?: number; offset?: number }
) {
  return serializeFilters({
    q,
    source,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    category: category || undefined,
    min_duration: minDuration ? Number(minDuration) : undefined,
    max_duration: maxDuration ? Number(maxDuration) : undefined,
    sort_by: sortBy,
    video_id: existing.video_id,
    limit: existing.limit,
    offset: existing.offset,
  });
}
