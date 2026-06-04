import { Link } from 'react-router-dom';
import type { SavedSearch } from '../../types/api';
import { formatDate, sourceLabel } from '../../features/archive/format';

type SavedSearchItemProps = {
  saved: SavedSearch;
  onDelete: () => void;
};

function savedSearchUrl(saved: SavedSearch) {
  const params = new URLSearchParams({ q: saved.query });
  Object.entries(saved.filters ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  return `/search?${params.toString()}`;
}

export default function SavedSearchItem({ saved, onDelete }: SavedSearchItemProps) {
  return (
    <div className="rounded-2xl border border-border bg-surface-muted p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-ink">{saved.query}</div>
          <div className="mt-1 text-sm text-muted">Saved {formatDate(saved.created_at ?? null)}</div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-subtle">
            {saved.filters.source && <span>{sourceLabel(saved.filters.source)}</span>}
            {saved.filters.category && <span>Type {saved.filters.category}</span>}
            {saved.filters.date_from && <span>From {saved.filters.date_from}</span>}
            {saved.filters.date_to && <span>To {saved.filters.date_to}</span>}
          </div>
        </div>
        <button type="button" className="nav-link text-danger" onClick={onDelete}>
          Delete
        </button>
      </div>
      <Link className="action-link mt-3 inline-block" to={savedSearchUrl(saved)}>
        Reopen search
      </Link>
    </div>
  );
}
