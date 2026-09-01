import type { FormEvent } from 'react';
import type { ArchiveSearchFilters } from '../../types/api';
type SearchFiltersPanelProps = {
  q: string;
  dateFrom: string;
  dateTo: string;
  matchMode: NonNullable<ArchiveSearchFilters['match_mode']>;
  sortBy: NonNullable<ArchiveSearchFilters['sort_by']>;
  loading: boolean;
  canSubmitSearch: boolean;
  onQChange: (value: string) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onMatchModeChange: (value: NonNullable<ArchiveSearchFilters['match_mode']>) => void;
  onSortByChange: (value: NonNullable<ArchiveSearchFilters['sort_by']>) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onReset: () => void;
};

export default function SearchFiltersPanel({
  q,
  dateFrom,
  dateTo,
  matchMode,
  sortBy,
  loading,
  canSubmitSearch,
  onQChange,
  onDateFromChange,
  onDateToChange,
  onMatchModeChange,
  onSortByChange,
  onSubmit,
  onReset,
}: SearchFiltersPanelProps) {
  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="archive-command">
        <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="flex min-w-0 items-center gap-3 px-3">
            <svg
              className="h-5 w-5 shrink-0 text-subtle"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="7" strokeWidth="1.8" />
              <path d="m20 20-4-4" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            <label className="sr-only" htmlFor="search-query">
              Search query
            </label>
            <input
              id="search-query"
              name="q"
              type="search"
              autoComplete="off"
              value={q}
              onChange={(event) => onQChange(event.target.value)}
              placeholder="Search a topic, quote, guest, or exact phrase…"
              className="min-h-[54px] w-full bg-transparent text-lg text-ink outline-none placeholder:text-subtle"
            />
          </div>
          <button
            type="submit"
            className="btn min-h-[54px] px-7"
            disabled={!canSubmitSearch || loading}
          >
            {loading ? 'Searching…' : 'Search archive'}
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="space-y-1.5 text-xs text-muted" htmlFor="search-match-mode">
            <span className="meta-label">Matching</span>
            <select
              id="search-match-mode"
              name="match_mode"
              className="form-control min-h-[42px] w-full"
              value={matchMode}
              onChange={(event) =>
                onMatchModeChange(
                  event.target.value as NonNullable<ArchiveSearchFilters['match_mode']>
                )
              }
            >
              <option value="topic">Topic</option>
              <option value="whole_word">Whole word</option>
              <option value="exact_phrase">Exact phrase</option>
            </select>
          </label>
          <label className="space-y-1.5 text-xs text-muted" htmlFor="search-date-from">
            <span className="meta-label">From</span>
            <input
              id="search-date-from"
              name="date_from"
              type="date"
              className="form-control min-h-[42px]"
              value={dateFrom}
              onChange={(event) => onDateFromChange(event.target.value)}
            />
          </label>
          <label className="space-y-1.5 text-xs text-muted" htmlFor="search-date-to">
            <span className="meta-label">To</span>
            <input
              id="search-date-to"
              name="date_to"
              type="date"
              className="form-control min-h-[42px]"
              value={dateTo}
              onChange={(event) => onDateToChange(event.target.value)}
            />
          </label>
          <label className="space-y-1.5 text-xs text-muted" htmlFor="search-sort-by">
            <span className="meta-label">Sort</span>
            <select
              id="search-sort-by"
              name="sort_by"
              className="form-control min-h-[42px] w-full"
              value={sortBy}
              onChange={(event) =>
                onSortByChange(event.target.value as NonNullable<ArchiveSearchFilters['sort_by']>)
              }
            >
              <option value="relevance">Relevance</option>
              <option value="date_desc">Newest</option>
              <option value="date_asc">Oldest</option>
              <option value="duration_desc">Longest</option>
              <option value="duration_asc">Shortest</option>
            </select>
          </label>
        </div>
        <p className="text-xs leading-5 text-muted sm:max-w-52">
          Topic finds related word forms, such as “housing” and “house”.
        </p>
        {(q || dateFrom || dateTo || matchMode !== 'topic' || sortBy !== 'relevance') && (
          <button
            type="button"
            className="btn-ghost self-start text-sm sm:self-auto"
            onClick={onReset}
          >
            Clear query and dates
          </button>
        )}
      </div>
    </form>
  );
}
