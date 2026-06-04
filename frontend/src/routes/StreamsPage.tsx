import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../services';
import type { PageInfo, VideoInfo } from '../types/api';
import { DEFAULT_LIMIT, parseFilters, type DateField, type FilterState } from '../features/streams/library';
import { StreamCard, StreamFiltersBar } from '../components/archive';

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

  function onSubmit(event: FormEvent) {
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
      <StreamFiltersBar
        itemsCount={items.length}
        totalCount={totalCount}
        pageNumber={pageNumber}
        totalPages={totalPages}
        q={q}
        completedOnly={completedOnly}
        dateField={dateField}
        dateFrom={dateFrom}
        dateTo={dateTo}
        category={category}
        onQChange={setQ}
        onCompletedOnlyChange={setCompletedOnly}
        onDateFieldChange={setDateField}
        onDateFromChange={setDateFrom}
        onDateToChange={setDateTo}
        onCategoryChange={setCategory}
        onSubmit={onSubmit}
        onReset={clearFilters}
      />

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
