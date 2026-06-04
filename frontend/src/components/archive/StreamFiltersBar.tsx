import type { FormEvent } from 'react';

type StreamFiltersBarProps = {
  itemsCount: number;
  totalCount: number;
  pageNumber: number;
  totalPages: number;
  q: string;
  dateFrom: string;
  dateTo: string;
  onQChange: (value: string) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onReset: () => void;
};

export default function StreamFiltersBar({
  itemsCount,
  totalCount,
  pageNumber,
  totalPages,
  q,
  dateFrom,
  dateTo,
  onQChange,
  onDateFromChange,
  onDateToChange,
  onSubmit,
  onReset,
}: StreamFiltersBarProps) {
  return (
    <header className="surface-card space-y-5 overflow-hidden">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl space-y-3">
          <div>
            <p className="mb-1 text-sm font-medium uppercase tracking-[0.24em] text-subtle">VOD library</p>
            <h1 className="page-title">Browse HasanAbi VODs</h1>
          </div>
          <p className="max-w-2xl text-muted">Search the HasanAbi archive and narrow by broadcast date.</p>
        </div>

        <div className="grid min-w-[14rem] grid-cols-2 gap-3 rounded-2xl border border-border bg-surface-muted/60 p-4 text-sm sm:grid-cols-4 lg:min-w-[30rem]">
          <div>
            <div className="text-xs uppercase tracking-wide text-subtle">Shown</div>
            <div className="mt-1 font-semibold text-ink">{itemsCount}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-subtle">Total</div>
            <div className="mt-1 font-semibold text-ink">{totalCount}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-subtle">Page</div>
            <div className="mt-1 font-semibold text-ink">{pageNumber} / {totalPages}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-subtle">Date</div>
            <div className="mt-1 font-semibold text-ink">Broadcast</div>
          </div>
        </div>
      </div>

      <form onSubmit={onSubmit} className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_10rem_10rem_auto]">
        <div className="lg:col-span-1">
          <label className="sr-only" htmlFor="stream-q">Search VODs</label>
          <input id="stream-q" type="search" placeholder="Search titles, channels, or notes…" className="form-control" aria-label="Search VODs" value={q} onChange={(event) => onQChange(event.target.value)} />
        </div>

        <div>
          <label className="sr-only" htmlFor="stream-date-from">Start date</label>
          <input id="stream-date-from" type="date" className="form-control" aria-label="From date" value={dateFrom} onChange={(event) => onDateFromChange(event.target.value)} />
        </div>

        <div>
          <label className="sr-only" htmlFor="stream-date-to">End date</label>
          <input id="stream-date-to" type="date" className="form-control" aria-label="To date" value={dateTo} onChange={(event) => onDateToChange(event.target.value)} />
        </div>

        <div className="flex flex-wrap gap-2 lg:justify-end">
          <button type="submit" className="btn-primary">Apply filters</button>
          <button type="button" className="btn-secondary" onClick={onReset}>Reset</button>
        </div>
      </form>
    </header>
  );
}
