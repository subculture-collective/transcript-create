import type { FormEvent } from 'react';
import type { ArchiveSearchFilters } from '../../types/api';

type SearchFiltersPanelProps = {
  q: string;
  source: ArchiveSearchFilters['source'];
  category: string;
  dateFrom: string;
  dateTo: string;
  minDuration: string;
  maxDuration: string;
  sortBy: string;
  loading: boolean;
  canSubmitSearch: boolean;
  onQChange: (value: string) => void;
  onSourceChange: (value: ArchiveSearchFilters['source']) => void;
  onCategoryChange: (value: string) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onMinDurationChange: (value: string) => void;
  onMaxDurationChange: (value: string) => void;
  onSortByChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onReset: () => void;
};

export default function SearchFiltersPanel({
  q,
  source,
  category,
  dateFrom,
  dateTo,
  minDuration,
  maxDuration,
  sortBy,
  loading,
  canSubmitSearch,
  onQChange,
  onSourceChange,
  onCategoryChange,
  onDateFromChange,
  onDateToChange,
  onMinDurationChange,
  onMaxDurationChange,
  onSortByChange,
  onSubmit,
  onReset,
}: SearchFiltersPanelProps) {
  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_12rem_11rem_auto]">
        <div>
          <label className="sr-only" htmlFor="search-query">
            Search query
          </label>
          <input
            id="search-query"
            type="search"
            value={q}
            onChange={(event) => onQChange(event.target.value)}
            placeholder="Search HasanAbi VODs..."
            className="form-control min-h-[48px] px-4 text-base tracking-[-0.02em]"
          />
        </div>

        <div>
          <label className="sr-only" htmlFor="search-source">
            Source
          </label>
          <select id="search-source" className="form-control min-h-[48px]" value={source ?? ''} onChange={(event) => onSourceChange((event.target.value || undefined) as ArchiveSearchFilters['source'])}>
            <option value="">Best available</option>
            <option value="native">Whisper transcript</option>
            <option value="youtube">YouTube captions</option>
          </select>
        </div>

        <div>
          <label className="sr-only" htmlFor="search-sort">
            Sort
          </label>
          <select id="search-sort" className="form-control min-h-[48px]" value={sortBy} onChange={(event) => onSortByChange(event.target.value)}>
            <option value="relevance">Best match</option>
            <option value="date_desc">Most recent</option>
            <option value="date_asc">Oldest</option>
            <option value="duration_desc">Longest</option>
            <option value="duration_asc">Shortest</option>
          </select>
        </div>

        <div className="flex gap-2 lg:justify-end">
          <button type="submit" className="btn min-h-[48px] px-5" disabled={!canSubmitSearch || loading}>
            Search
          </button>
          <button type="button" className="btn-secondary min-h-[48px] px-4" onClick={onReset}>
            Reset
          </button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
        <input id="search-category" type="text" className="form-control" value={category} onChange={(event) => onCategoryChange(event.target.value)} placeholder="VOD type" aria-label="VOD type" />
        <input id="search-date-from" type="date" className="form-control" value={dateFrom} onChange={(event) => onDateFromChange(event.target.value)} aria-label="From date" />
        <input id="search-date-to" type="date" className="form-control" value={dateTo} onChange={(event) => onDateToChange(event.target.value)} aria-label="To date" />
        <input id="search-min-duration" type="number" min="0" step="1" inputMode="numeric" placeholder="Min seconds" className="form-control" value={minDuration} onChange={(event) => onMinDurationChange(event.target.value)} aria-label="Minimum duration" />
        <input id="search-max-duration" type="number" min="0" step="1" inputMode="numeric" placeholder="Max seconds" className="form-control" value={maxDuration} onChange={(event) => onMaxDurationChange(event.target.value)} aria-label="Maximum duration" />
      </div>

      <div className="flex flex-wrap gap-1.5 text-sm text-muted">
        <span className="source-pill">grouped by VOD</span>
        <span className="source-pill">timestamp pills</span>
        <span className="match-pill">highlighted snippets</span>
      </div>
    </form>
  );
}
