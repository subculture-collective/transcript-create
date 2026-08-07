import type { FormEvent } from 'react';
type SearchFiltersPanelProps = {
  q: string;
  dateFrom: string;
  dateTo: string;
  matchMode: 'topic' | 'exact_phrase' | 'whole_word';
  loading: boolean;
  canSubmitSearch: boolean;
  onQChange: (value: string) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onMatchModeChange: (value: 'topic' | 'exact_phrase' | 'whole_word') => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onReset: () => void;
};

export default function SearchFiltersPanel({
  q,
  dateFrom,
  dateTo,
  matchMode,
  loading,
  canSubmitSearch,
  onQChange,
  onDateFromChange,
  onDateToChange,
  onMatchModeChange,
  onSubmit,
  onReset,
}: SearchFiltersPanelProps) {
  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
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

        <div className="flex gap-2 lg:justify-end">
          <button
            type="submit"
            className="btn min-h-[48px] px-5"
            disabled={!canSubmitSearch || loading}
          >
            Search
          </button>
          <button type="button" className="btn-secondary min-h-[48px] px-4" onClick={onReset}>
            Reset
          </button>
        </div>
      </div>

      <fieldset className="flex flex-wrap gap-2" aria-describedby="matching-rule-help">
        <legend className="sr-only">Matching rule</legend>
        {(
          [
            ['topic', 'Topic', 'Includes related word forms such as house and housing.'],
            ['exact_phrase', 'Exact phrase', 'Matches these words together in this order.'],
            ['whole_word', 'Whole words', 'Matches complete words without stemming.'],
          ] as const
        ).map(([value, label, description]) => (
          <label
            key={value}
            className={`search-mode-option ${matchMode === value ? 'search-mode-option-active' : ''}`}
          >
            <input
              type="radio"
              name="match-mode"
              value={value}
              checked={matchMode === value}
              onChange={() => onMatchModeChange(value)}
            />
            <span>
              <strong>{label}</strong>
              <small>{description}</small>
            </span>
          </label>
        ))}
      </fieldset>
      <p id="matching-rule-help" className="text-xs text-subtle">
        The selected matching rule is recorded in the URL so shared searches stay reproducible.
      </p>

      <details className="filter-disclosure" open={Boolean(dateFrom || dateTo)}>
        <summary>Filters</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <input
            id="search-date-from"
            type="date"
            className="form-control min-h-[48px]"
            value={dateFrom}
            onChange={(event) => onDateFromChange(event.target.value)}
            aria-label="From date"
          />
          <input
            id="search-date-to"
            type="date"
            className="form-control min-h-[48px]"
            value={dateTo}
            onChange={(event) => onDateToChange(event.target.value)}
            aria-label="To date"
          />
        </div>
      </details>
    </form>
  );
}
