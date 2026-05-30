import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../services';
import type { PageInfo, StreamLibraryFilters, VideoInfo } from '../types/api';

const DEFAULT_LIMIT = 24;
const DATE_FIELD_OPTIONS = [
  { value: 'uploaded_at', label: 'Uploaded date' },
  { value: 'created_at', label: 'Created date' },
  { value: 'updated_at', label: 'Updated date' },
] as const;

type DateField = NonNullable<StreamLibraryFilters['date_field']>;

type FilterState = {
  q: string;
  completedOnly: boolean;
  dateField: DateField;
  dateFrom: string;
  dateTo: string;
};

function formatDuration(seconds?: number | null) {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
    : `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}

function formatDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date);
}

function titleCase(value: string) {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function parseFilters(params: URLSearchParams): FilterState {
  const dateFieldParam = params.get('date_field');
  const dateField = DATE_FIELD_OPTIONS.some((option) => option.value === dateFieldParam)
    ? (dateFieldParam as DateField)
    : 'uploaded_at';

  return {
    q: params.get('q') ?? '',
    completedOnly: params.get('completed_only') === 'true',
    dateField,
    dateFrom: params.get('date_from') ?? '',
    dateTo: params.get('date_to') ?? '',
  };
}

function statusBadge(video: VideoInfo) {
  const states = [video.state, video.caption_ingest_state, video.diarization_state]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase());

  if (states.some((value) => /error|failed|cancel/.test(value))) {
    return { label: 'Needs attention', className: 'rounded-full bg-danger-soft px-2 py-1 font-medium text-danger' };
  }

  if (states.some((value) => /ready|complete|done|finished/.test(value))) {
    return { label: 'Ready', className: 'badge-success' };
  }

  if (states.some((value) => /process|queue|pending|transcrib|ingest|sync/.test(value))) {
    return { label: 'Processing', className: 'badge-warning' };
  }

  return {
    label: titleCase(video.state ?? 'Unknown'),
    className: 'rounded-full bg-surface-muted px-2 py-1 font-medium text-muted',
  };
}

function dateFieldLabel(field: DateField) {
  return DATE_FIELD_OPTIONS.find((option) => option.value === field)?.label ?? titleCase(field);
}

export default function StreamsPage() {
  const [params, setParams] = useSearchParams();
  const searchKey = params.toString();
  const filters = useMemo(() => parseFilters(params), [searchKey]);

  const [q, setQ] = useState(filters.q);
  const [completedOnly, setCompletedOnly] = useState(filters.completedOnly);
  const [dateField, setDateField] = useState<DateField>(filters.dateField);
  const [dateFrom, setDateFrom] = useState(filters.dateFrom);
  const [dateTo, setDateTo] = useState(filters.dateTo);
  const [items, setItems] = useState<VideoInfo[]>([]);
  const [pageInfo, setPageInfo] = useState<PageInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setQ(filters.q);
    setCompletedOnly(filters.completedOnly);
    setDateField(filters.dateField);
    setDateFrom(filters.dateFrom);
    setDateTo(filters.dateTo);
  }, [filters.q, filters.completedOnly, filters.dateField, filters.dateFrom, filters.dateTo]);

  useEffect(() => {
    setLoading(true);
    setError(null);

    api
      .listStreamLibrary({
        limit: DEFAULT_LIMIT,
        offset: Math.max(0, Number(params.get('offset') ?? '0') || 0),
        completed_only: filters.completedOnly,
        q: filters.q || undefined,
        date_field: filters.dateField,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
      })
      .then((response) => {
        setItems(response.items);
        setPageInfo(response.page_info);
      })
      .catch((err: unknown) => {
        console.error('Failed to load stream library', err);
        setError('Failed to load streams.');
        setItems([]);
        setPageInfo(null);
      })
      .finally(() => setLoading(false));
  }, [filters.completedOnly, filters.dateField, filters.dateFrom, filters.dateTo, filters.q, params]);

  const offset = Math.max(0, Number(params.get('offset') ?? '0') || 0);
  const totalCount = pageInfo?.total_count ?? items.length;
  const startItem = totalCount === 0 ? 0 : offset + 1;
  const endItem = Math.min(offset + items.length, totalCount);
  const pageNumber = Math.floor(offset / DEFAULT_LIMIT) + 1;
  const totalPages = Math.max(1, Math.ceil(Math.max(totalCount, 1) / DEFAULT_LIMIT));

  function updateParams(next: Partial<FilterState> & { offset?: number }) {
    const nextParams = new URLSearchParams();
    const nextFilters = {
      q: next.q ?? q,
      completedOnly: next.completedOnly ?? completedOnly,
      dateField: next.dateField ?? dateField,
      dateFrom: next.dateFrom ?? dateFrom,
      dateTo: next.dateTo ?? dateTo,
    };

    if (nextFilters.q.trim()) nextParams.set('q', nextFilters.q.trim());
    if (!nextFilters.completedOnly) nextParams.set('completed_only', 'false');
    if (nextFilters.dateField) nextParams.set('date_field', nextFilters.dateField);
    if (nextFilters.dateFrom) nextParams.set('date_from', nextFilters.dateFrom);
    if (nextFilters.dateTo) nextParams.set('date_to', nextFilters.dateTo);

    const nextOffset = next.offset ?? 0;
    if (nextOffset > 0) nextParams.set('offset', String(nextOffset));

    setParams(nextParams);
  }

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    updateParams({ offset: 0 });
  }

  function clearFilters() {
    const nextParams = new URLSearchParams();
    setQ('');
    setCompletedOnly(false);
    setDateField('uploaded_at');
    setDateFrom('');
    setDateTo('');
    setParams(nextParams);
  }

  return (
    <div className="space-y-6">
      <header className="surface-card space-y-5 overflow-hidden">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-3">
            <div>
              <p className="mb-1 text-sm font-medium uppercase tracking-[0.24em] text-subtle">
                Stream library
              </p>
              <h1 className="page-title">Browse recorded streams</h1>
            </div>
            <p className="max-w-2xl text-muted">
              Search the full archive, narrow by date range, and scan transcript readiness at a glance.
            </p>
          </div>

          <div className="grid min-w-[14rem] grid-cols-2 gap-3 rounded-2xl border border-border bg-surface-muted/60 p-4 text-sm sm:grid-cols-4 lg:min-w-[30rem]">
            <div>
              <div className="text-xs uppercase tracking-wide text-subtle">Shown</div>
              <div className="mt-1 font-semibold text-ink">{items.length}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-subtle">Total</div>
              <div className="mt-1 font-semibold text-ink">{totalCount}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-subtle">Page</div>
              <div className="mt-1 font-semibold text-ink">
                {pageNumber} / {totalPages}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-subtle">Date</div>
              <div className="mt-1 font-semibold text-ink">{dateFieldLabel(dateField)}</div>
            </div>
          </div>
        </div>

        <form onSubmit={onSubmit} className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_repeat(4,minmax(0,1fr))_auto]">
          <div className="lg:col-span-1">
            <label className="sr-only" htmlFor="stream-q">
              Search streams
            </label>
            <input
              id="stream-q"
              type="search"
              placeholder="Search titles, channels, or notes…"
              className="form-control"
              aria-label="Search streams"
              value={q}
              onChange={(event) => setQ(event.target.value)}
            />
          </div>

          <div>
            <label className="sr-only" htmlFor="stream-date-field">
              Date field
            </label>
            <select
              id="stream-date-field"
              className="form-control"
              value={dateField}
              onChange={(event) => setDateField(event.target.value as DateField)}
            >
              {DATE_FIELD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="sr-only" htmlFor="stream-date-from">
              Start date
            </label>
            <input
              id="stream-date-from"
              type="date"
              className="form-control"
              aria-label="From date"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </div>

          <div>
            <label className="sr-only" htmlFor="stream-date-to">
              End date
            </label>
            <input
              id="stream-date-to"
              type="date"
              className="form-control"
              aria-label="To date"
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </div>

          <label className="flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-3 text-sm text-muted">
            <input
              type="checkbox"
              checked={completedOnly}
              onChange={(event) => setCompletedOnly(event.target.checked)}
              className="h-4 w-4 rounded border-border text-accent focus:ring-accent"
            />
            Completed only
          </label>

          <div className="flex flex-wrap gap-2 lg:justify-end">
            <button type="submit" className="btn-primary">
              Apply filters
            </button>
            <button type="button" className="btn-secondary" onClick={clearFilters}>
              Reset
            </button>
          </div>
        </form>
      </header>

      <div className="flex flex-col gap-3 rounded-2xl border border-border bg-surface px-4 py-3 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
        <div>
          {loading ? 'Loading streams…' : error ? error : `${startItem}-${endItem} of ${totalCount} streams`}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn-secondary"
            disabled={offset === 0 || loading}
            onClick={() => updateParams({ offset: Math.max(0, offset - DEFAULT_LIMIT) })}
          >
            Previous
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={!pageInfo?.has_next_page || loading}
            onClick={() => updateParams({ offset: offset + DEFAULT_LIMIT })}
          >
            Next
          </button>
        </div>
      </div>

      {loading && items.length === 0 ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="surface-card-compact animate-pulse space-y-3">
              <div className="aspect-video rounded-xl bg-surface-muted" />
              <div className="h-4 w-5/6 rounded bg-surface-muted" />
              <div className="h-3 w-3/5 rounded bg-surface-muted" />
              <div className="h-3 w-2/5 rounded bg-surface-muted" />
            </div>
          ))}
        </div>
      ) : items.length > 0 ? (
        <section aria-label="Stream results" className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((video) => {
            const status = statusBadge(video);
            const title = video.title || `Video ${video.youtube_id}`;
            const dateValue = video[dateField];

            return (
              <article
                key={video.id}
                className="surface-card-compact group flex h-full flex-col overflow-hidden border border-border/80 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent hover:shadow-lg"
              >
                <div className="relative overflow-hidden rounded-xl border border-border/60 bg-surface-muted">
                  <img
                    src={`https://i.ytimg.com/vi/${video.youtube_id}/hqdefault.jpg`}
                    alt={title}
                    loading="lazy"
                    className="aspect-video w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                  />
                  <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 bg-gradient-to-t from-black/75 via-black/25 to-transparent px-3 py-2 text-xs text-white">
                    <span className="rounded-full bg-black/60 px-2 py-1 font-medium backdrop-blur">
                      {formatDuration(video.duration_seconds)}
                    </span>
                    <span className="rounded-full bg-black/60 px-2 py-1 font-medium backdrop-blur">
                      {dateFieldLabel(dateField)} {formatDate(dateValue ?? null)}
                    </span>
                  </div>
                </div>

                <div className="flex flex-1 flex-col gap-4 p-4">
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-2">
                      <span className={status.className}>{status.label}</span>
                      <span
                        className={
                          video.has_whisper_transcript
                            ? 'badge-success'
                            : 'rounded-full bg-surface-muted px-2 py-1 font-medium text-muted'
                        }
                      >
                        {video.has_whisper_transcript ? 'Whisper transcript' : 'No Whisper transcript'}
                      </span>
                      <span
                        className={
                          video.has_youtube_transcript
                            ? 'badge-warning'
                            : 'rounded-full bg-surface-muted px-2 py-1 font-medium text-muted'
                        }
                      >
                        {video.has_youtube_transcript ? 'YouTube captions' : 'No YouTube captions'}
                      </span>
                      {!video.has_whisper_transcript && !video.has_youtube_transcript && (
                        <span className="rounded-full bg-danger-soft px-2 py-1 font-medium text-danger">
                          No transcript yet
                        </span>
                      )}
                    </div>

                    <h2 className="line-clamp-2 text-lg font-semibold tracking-tight text-ink group-hover:text-accent">
                      <Link to={`/v/${video.id}`} className="hover:underline focus:underline">
                        {title}
                      </Link>
                    </h2>
                    <div className="text-sm text-muted">
                      <div className="line-clamp-1">{video.channel_name || 'Unknown channel'}</div>
                    </div>
                  </div>

                  <div className="mt-auto space-y-2 text-sm text-muted">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span>{formatDate(dateValue ?? null)}</span>
                      {video.updated_at && <span>Updated {formatDate(video.updated_at)}</span>}
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-xs uppercase tracking-wide text-subtle">
                      <span>{video.youtube_id.slice(0, 8)}</span>
                      <Link to={`/v/${video.id}`} className="action-link group-hover:underline">
                        Open stream
                      </Link>
                      {video.has_whisper_transcript && (
                        <Link
                          to={`/?source=native&q=${encodeURIComponent(title)}`}
                          className="action-link"
                        >
                          Search Whisper
                        </Link>
                      )}
                      {video.has_youtube_transcript && (
                        <Link
                          to={`/?source=youtube&q=${encodeURIComponent(title)}`}
                          className="action-link"
                        >
                          Search YouTube captions
                        </Link>
                      )}
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      ) : (
        <div className="surface-card text-center">
          <p className="text-lg font-medium text-ink">No streams match these filters.</p>
          <p className="mt-2 text-muted">Try broadening the date range or clearing completed-only.</p>
        </div>
      )}

      <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted">
          Showing {startItem === 0 ? 0 : startItem}-{endItem} of {totalCount}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn-secondary"
            disabled={offset === 0 || loading}
            onClick={() => updateParams({ offset: Math.max(0, offset - DEFAULT_LIMIT) })}
          >
            Previous page
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={!pageInfo?.has_next_page || loading}
            onClick={() => updateParams({ offset: offset + DEFAULT_LIMIT })}
          >
            Next page
          </button>
        </div>
      </div>
    </div>
  );
}
