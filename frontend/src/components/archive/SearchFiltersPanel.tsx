import type { FormEvent } from 'react';
type SearchFiltersPanelProps = {
  q: string;
  dateFrom: string;
  dateTo: string;
  loading: boolean;
  canSubmitSearch: boolean;
  onQChange: (value: string) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onReset: () => void;
};

export default function SearchFiltersPanel({
  q,
  dateFrom,
  dateTo,
  loading,
  canSubmitSearch,
  onQChange,
  onDateFromChange,
  onDateToChange,
  onSubmit,
  onReset,
}: SearchFiltersPanelProps) {
  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_10rem_10rem_auto]">
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

        <input id="search-date-from" type="date" className="form-control min-h-[48px]" value={dateFrom} onChange={(event) => onDateFromChange(event.target.value)} aria-label="From date" />
        <input id="search-date-to" type="date" className="form-control min-h-[48px]" value={dateTo} onChange={(event) => onDateToChange(event.target.value)} aria-label="To date" />

        <div className="flex gap-2 lg:justify-end">
          <button type="submit" className="btn min-h-[48px] px-5" disabled={!canSubmitSearch || loading}>
            Search
          </button>
          <button type="button" className="btn-secondary min-h-[48px] px-4" onClick={onReset}>
            Reset
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 text-sm text-muted">
        <span className="source-pill">grouped by VOD</span>
        <span className="source-pill">timestamp pills</span>
        <span className="match-pill">highlighted snippets</span>
      </div>
    </form>
  );
}
