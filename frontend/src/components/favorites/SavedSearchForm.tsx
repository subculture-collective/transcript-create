import type { SavedSearchFilters } from '../../types/api';

type SavedSearchFormProps = {
  query: string;
  filters: SavedSearchFilters;
  saving: boolean;
  onQueryChange: (value: string) => void;
  onFiltersChange: (updater: (current: SavedSearchFilters) => SavedSearchFilters) => void;
  onSave: () => void;
};

export default function SavedSearchForm({ query, filters, saving, onQueryChange, onFiltersChange, onSave }: SavedSearchFormProps) {
  return (
    <div className="space-y-3 rounded-2xl border border-border bg-surface-muted p-4">
      <div className="text-xs uppercase tracking-[0.24em] text-subtle">Save current search</div>
      <label className="block text-sm text-muted">
        Query
        <input className="form-control mt-1" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Enter a search term" />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm text-muted">
          From date
          <input className="form-control mt-1" type="date" value={filters.date_from ?? ''} onChange={(event) => onFiltersChange((current) => ({ ...current, date_from: event.target.value || undefined }))} />
        </label>
        <label className="block text-sm text-muted">
          To date
          <input className="form-control mt-1" type="date" value={filters.date_to ?? ''} onChange={(event) => onFiltersChange((current) => ({ ...current, date_to: event.target.value || undefined }))} />
        </label>
      </div>
      <button type="button" className="btn w-full" onClick={onSave} disabled={saving || !query.trim()}>
        {saving ? 'Saving…' : 'Save search'}
      </button>
    </div>
  );
}
