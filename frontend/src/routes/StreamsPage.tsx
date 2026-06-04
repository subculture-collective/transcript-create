import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../services';
import type { PageInfo, VideoInfo } from '../types/api';
import { DEFAULT_LIMIT, DATE_FIELD_OPTIONS, dateFieldLabel, parseFilters, type DateField, type FilterState } from '../features/streams/library';
import { StreamCard } from '../components/archive';

export default function StreamsPage() {
  const [params, setParams] = useSearchParams();
  const searchKey = params.toString();
  const filters = useMemo(() => parseFilters(params), [searchKey]);

  const [q, setQ] = useState(filters.q);
  const [completedOnly, setCompletedOnly] = useState(filters.completedOnly);
  const [dateField, setDateField] = useState<DateField>(filters.dateField);
  const [dateFrom, setDateFrom] = useState(filters.dateFrom);
  const [dateTo, setDateTo] = useState(filters.dateTo);
  const [category, setCategory] = useState(filters.category);
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
    setCategory(filters.category);
  }, [filters.q, filters.completedOnly, filters.dateField, filters.dateFrom, filters.dateTo, filters.category]);

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
        category: filters.category || undefined,
      })
      .then((response) => {
        setItems(response.items);
        setPageInfo(response.page_info);
      })
      .catch((err: unknown) => {
        console.error('Failed to load stream library', err);
        setError('Failed to load VODs.');
        setItems([]);
        setPageInfo(null);
      })
      .finally(() => setLoading(false));
  }, [filters.completedOnly, filters.dateField, filters.dateFrom, filters.dateTo, filters.category, filters.q, params]);

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
      category: next.category ?? category,
    };

    if (nextFilters.q.trim()) nextParams.set('q', nextFilters.q.trim());
    if (!nextFilters.completedOnly) nextParams.set('completed_only', 'false');
    if (nextFilters.dateField) nextParams.set('date_field', nextFilters.dateField);
    if (nextFilters.dateFrom) nextParams.set('date_from', nextFilters.dateFrom);
    if (nextFilters.dateTo) nextParams.set('date_to', nextFilters.dateTo);
    if (nextFilters.category.trim()) nextParams.set('category', nextFilters.category.trim());

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
    setCategory('');
    setParams(nextParams);
  }

  return (
    <div className="space-y-6">
      <header className="surface-card space-y-5 overflow-hidden">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-3">
            <div>
              <p className="mb-1 text-sm font-medium uppercase tracking-[0.24em] text-subtle">
                VOD library
              </p>
              <h1 className="page-title">Browse HasanAbi VODs</h1>
            </div>
            <p className="max-w-2xl text-muted">
              Search the HasanAbi archive, narrow by date range, and scan transcript readiness at a glance.
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

        <form onSubmit={onSubmit} className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_repeat(5,minmax(0,1fr))_auto]">
          <div className="lg:col-span-1">
            <label className="sr-only" htmlFor="stream-q">
              Search VODs
            </label>
            <input
              id="stream-q"
              type="search"
              placeholder="Search titles, channels, or notes…"
              className="form-control"
              aria-label="Search VODs"
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
            <label className="sr-only" htmlFor="stream-category">
              VOD type
            </label>
            <input
              id="stream-category"
              type="text"
              className="form-control"
              aria-label="VOD type"
              placeholder="VOD type"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            />
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
          {loading ? 'Loading VODs…' : error ? error : `${startItem}-${endItem} of ${totalCount} VODs`}
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
          {items.map((video) => (
            <StreamCard key={video.id} video={video} dateField={dateField} />
          ))}
        </section>
      ) : (
        <div className="surface-card text-center">
          <p className="text-lg font-medium text-ink">No VODs match these filters.</p>
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
