import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  apiCreateSavedSearch,
  apiAddFavorite,
  apiDeleteFavorite,
  apiDeleteSavedSearch,
  apiListFavorites,
  apiListSavedSearches,
  favorites,
  localSavedSearches,
  savedSearchKey,
  useAuth,
} from '../services';
import type { SavedSearch, SavedSearchFilters } from '../types/api';
import { SavedMomentItem, SavedSearchForm, SavedSearchItem } from '../components/favorites';
import { AsyncError, AsyncStatus } from '../components/async/AsyncFeedback';

function readSavedSearchFilters(params: URLSearchParams): {
  query: string;
  filters: SavedSearchFilters;
} {
  return {
    query: params.get('query') ?? params.get('q') ?? '',
    filters: {
      source: (params.get('source') as SavedSearchFilters['source']) ?? undefined,
      category: params.get('category') ?? undefined,
      date_from: params.get('date_from') ?? undefined,
      date_to: params.get('date_to') ?? undefined,
      min_duration: params.get('min_duration') ? Number(params.get('min_duration')) : undefined,
      max_duration: params.get('max_duration') ? Number(params.get('max_duration')) : undefined,
      sort_by: params.get('sort_by') ?? undefined,
      video_id: params.get('video_id') ?? undefined,
      limit: params.get('limit') ? Number(params.get('limit')) : undefined,
      offset: params.get('offset') ? Number(params.get('offset')) : undefined,
    },
  };
}

export default function FavoritesPage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const [items, setItems] = useState(favorites.list());
  const [remote, setRemote] = useState<Array<{
    id: string;
    video_id: string;
    start_ms: number;
    end_ms: number;
    text?: string;
  }> | null>(null);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[] | null>(null);
  const [localSearches, setLocalSearches] = useState(localSavedSearches.list());
  const [query, setQuery] = useState(readSavedSearchFilters(params).query);
  const [filters, setFilters] = useState<SavedSearchFilters>(
    readSavedSearchFilters(params).filters
  );
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [syncState, setSyncState] = useState<'idle' | 'loading' | 'synced' | 'error'>('idle');
  const [retryMutation, setRetryMutation] = useState<{
    label: string;
    action: () => void;
  } | null>(null);
  const visibleSearches = user ? (savedSearches ?? localSearches) : localSearches;

  useEffect(() => {
    const next = readSavedSearchFilters(params);
    setQuery(next.query);
    setFilters(next.filters);
  }, [params]);

  const synchronize = useCallback(async () => {
    if (!user) return;
    setSyncState('loading');
    setFeedback(null);
    const [moments, searches] = await Promise.allSettled([
      apiListFavorites().then(async (response) => {
        const serverKeys = new Set(
          response.items.map((item) => `${item.video_id}:${item.start_ms}:${item.end_ms}`)
        );
        for (const local of favorites.list()) {
          const key = `${local.videoId}:${local.startMs}:${local.endMs}`;
          if (!serverKeys.has(key)) {
            await apiAddFavorite({
              video_id: local.videoId,
              start_ms: local.startMs,
              end_ms: local.endMs,
              text: local.text,
            });
          }
          favorites.remove(local);
        }
        const refreshed = await apiListFavorites();
        setItems(favorites.list());
        setRemote(refreshed.items);
        if (serverKeys.size || refreshed.items.length) setFeedback('Saved moments synchronized.');
      }),
      apiListSavedSearches().then(async (response) => {
        const serverKeys = new Set(
          response.items.map((item) => savedSearchKey(item.query, item.filters))
        );
        for (const local of localSavedSearches.list()) {
          const key = savedSearchKey(local.query, local.filters);
          if (!serverKeys.has(key)) {
            await apiCreateSavedSearch({ query: local.query, filters: local.filters });
          }
          localSavedSearches.remove(local.id);
        }
        const refreshed = await apiListSavedSearches();
        setLocalSearches(localSavedSearches.list());
        setSavedSearches(refreshed.items);
      }),
    ]);
    if (moments.status === 'rejected') setRemote(null);
    if (searches.status === 'rejected') setSavedSearches(null);
    if (moments.status === 'rejected' || searches.status === 'rejected') {
      setSyncState('error');
      return;
    }
    setSyncState('synced');
  }, [user]);

  useEffect(() => {
    if (user) {
      void synchronize();
    } else {
      setRemote(null);
      setSavedSearches(null);
      setSyncState('idle');
    }
  }, [synchronize, user]);

  useEffect(() => {
    if (!user) {
      const synchronizeLocalState = (event: StorageEvent) => {
        if (event.key === null || event.key === 'favorites:v1') setItems(favorites.reload());
        if (event.key === null || event.key === 'saved-searches:v1')
          setLocalSearches(localSavedSearches.reload());
      };
      window.addEventListener('storage', synchronizeLocalState);
      return () => window.removeEventListener('storage', synchronizeLocalState);
    }
  }, [user]);

  async function saveSearch() {
    const trimmed = query.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      if (user) {
        await apiCreateSavedSearch({ query: trimmed, filters });
        const next = await apiListSavedSearches();
        setSavedSearches(next.items);
        setFeedback('Search saved and synchronized.');
      } else {
        localSavedSearches.add(trimmed, filters);
        setLocalSearches(localSavedSearches.list());
        setFeedback('Search saved in this browser.');
      }
    } catch {
      setFeedback('The search could not be saved. Try again.');
    } finally {
      setSaving(false);
    }
  }

  async function removeRemoteFavorite(id: string) {
    try {
      await apiDeleteFavorite(id);
      setRemote((current) => current?.filter((item) => item.id !== id) ?? current);
      setFeedback('Saved moment removed.');
      setRetryMutation(null);
    } catch {
      setFeedback('The saved moment could not be removed. It is still saved.');
      setRetryMutation({
        label: 'Retry removing saved moment',
        action: () => void removeRemoteFavorite(id),
      });
    }
  }

  async function removeRemoteSavedSearch(id: string) {
    try {
      await apiDeleteSavedSearch(id);
      setSavedSearches((current) => current?.filter((item) => item.id !== id) ?? current);
      setFeedback('Saved search removed.');
      setRetryMutation(null);
    } catch {
      setFeedback('The saved search could not be removed. It is still saved.');
      setRetryMutation({
        label: 'Retry removing saved search',
        action: () => void removeRemoteSavedSearch(id),
      });
    }
  }

  return (
    <div className="space-y-6">
      <section className="surface-card space-y-3">
        <div className="text-xs uppercase tracking-[0.24em] text-subtle">Saved</div>
        <h1 className="page-title">Saved moments and searches</h1>
        <p className="max-w-2xl text-muted">
          Keep interesting moments handy and preserve the searches that matter.
        </p>
      </section>

      {syncState === 'error' && (
        <AsyncError onRetry={() => void synchronize()} retryLabel="Retry synchronization">
          Your saved data could not be synchronized. Local saves are still available in this
          browser, but are not synchronized to your account.
        </AsyncError>
      )}

      {feedback && !retryMutation && (
        <div className="alert-warning" role="alert" aria-live="polite">
          {feedback}
        </div>
      )}
      {retryMutation && (
        <AsyncError onRetry={retryMutation.action} retryLabel={retryMutation.label}>
          {feedback}
        </AsyncError>
      )}

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(18rem,0.9fr)]">
        <div className="surface-card space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="section-title">Saved moments</h2>
            <Link to="/search" className="action-link text-sm">
              Search archive
            </Link>
          </div>

          {user && syncState === 'loading' && (
            <AsyncStatus>Synchronizing saved moments…</AsyncStatus>
          )}
          {user && syncState === 'error' && <p className="text-sm text-warning">Sync error</p>}

          {user && remote !== null ? (
            remote.length === 0 ? (
              <p className="text-muted">No saved moments yet.</p>
            ) : (
              <ul className="space-y-3">
                {remote.map((f) => (
                  <SavedMomentItem
                    key={f.id}
                    mode="remote"
                    item={f}
                    onRemove={() => void removeRemoteFavorite(f.id)}
                  />
                ))}
              </ul>
            )
          ) : (
            <>
              {items.length === 0 && <p className="text-muted">No saved moments yet.</p>}
              <ul className="space-y-3">
                {items.map((f, i) => (
                  <SavedMomentItem
                    key={i}
                    mode="local"
                    item={f}
                    onRemove={() => {
                      favorites.toggle(f);
                      setItems(favorites.list());
                    }}
                  />
                ))}
              </ul>
            </>
          )}
        </div>

        <section aria-label="Saved search tools" className="space-y-6">
          <div className="surface-card space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="section-title">Saved searches</h2>
              {user && syncState === 'synced' && savedSearches !== null ? (
                <span className="badge-success">Synced</span>
              ) : user && syncState === 'error' ? (
                <span className="badge-warning">Sync error</span>
              ) : user && syncState === 'loading' ? (
                <span className="badge-warning">Synchronizing</span>
              ) : user ? (
                <span className="badge-warning">Sync pending</span>
              ) : (
                <span className="badge-warning">Local only</span>
              )}
            </div>

            <>
              <SavedSearchForm
                query={query}
                filters={filters}
                saving={saving}
                onQueryChange={setQuery}
                onFiltersChange={setFilters}
                onSave={saveSearch}
              />

              {visibleSearches.length ? (
                <div className="space-y-3">
                  {visibleSearches.map((saved) => (
                    <SavedSearchItem
                      key={saved.id}
                      saved={saved}
                      onDelete={async () => {
                        if (user) {
                          await removeRemoteSavedSearch(saved.id);
                        } else {
                          localSavedSearches.remove(saved.id);
                          setLocalSearches(localSavedSearches.list());
                        }
                      }}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-muted">No saved searches yet.</p>
              )}
              {!user && <p className="text-sm text-muted">Sign in to synchronize local saves.</p>}
            </>
          </div>
        </section>
      </section>
    </div>
  );
}
