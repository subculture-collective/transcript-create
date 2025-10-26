import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, track } from '../services';
import type { SearchHit } from '../types/api';
// track imported via services barrel

function msToTimestamp(ms: number) {
  const s = Math.floor(ms / 1000);
  const hh = Math.floor(s / 3600)
    .toString()
    .padStart(2, '0');
  const mm = Math.floor((s % 3600) / 60)
    .toString()
    .padStart(2, '0');
  const ss = (s % 60).toString().padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') ?? '');
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [source, setSource] = useState<'native' | 'youtube'>(() =>
    params.get('source') === 'youtube' ? 'youtube' : 'native'
  );
  const [loading, setLoading] = useState(false);
  const [quotaError, setQuotaError] = useState<{
    message: string;
    used: number;
    limit: number;
  } | null>(null);

  const grouped = useMemo(() => {
    const g = new Map<string, SearchHit[]>();
    for (const h of hits) {
      const key = h.video_id;
      g.set(key, [...(g.get(key) ?? []), h]);
    }
    return Array.from(g.entries());
  }, [hits]);

  useEffect(() => {
    const query = params.get('q');
    if (!query) return;
    setLoading(true);
    setQuotaError(null);
    track({ type: 'search', payload: { q: query, source } });
    api
      .search(query, { source })
      .then((res: { hits: SearchHit[] }) => setHits(res.hits))
      .catch(async (err: unknown) => {
        const e = err as { response?: { status?: number; json: () => Promise<{ limit?: number; used?: number; message?: string }> } };
        if (e?.response?.status === 402) {
          const data = await e.response.json().catch(() => null);
          if (data?.limit != null)
            setQuotaError({
              message: data.message || 'Upgrade required',
              used: data.used || 0,
              limit: data.limit || 0,
            });
        } else {
          console.error(e);
        }
      })
      .finally(() => setLoading(false));
  }, [params, source]);

  // Keyboard shortcut: / to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault();
        document.getElementById('search-input')?.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next = new URLSearchParams(params);
    if (q) next.set('q', q);
    else next.delete('q');
    setParams(next);
  }

  function clearSearch() {
    setQ('');
    const next = new URLSearchParams(params);
    next.delete('q');
    setParams(next);
  }

  return (
    <div className="space-y-6">
      <div className="mb-8">
        <h1 className="text-3xl md:text-4xl font-bold mb-2">Search Transcripts</h1>
        <p className="text-stone-600 dark:text-stone-400">
          Search through millions of YouTube video transcripts
          <span className="ml-2 text-sm text-stone-500 dark:text-stone-500">
            (Press <kbd className="px-1.5 py-0.5 text-xs rounded bg-stone-200 dark:bg-stone-800 border border-stone-300 dark:border-stone-700 font-mono">/</kbd> to focus search)
          </span>
        </p>
      </div>

      <form onSubmit={onSubmit} className="flex flex-col sm:flex-row gap-2">
        <div className="relative flex-1">
          <input
            id="search-input"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search transcripts…"
            className="w-full rounded-md border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 px-3 py-3 pr-10 focus:border-blue-600 dark:focus:border-blue-400 focus:ring-2 focus:ring-blue-600 dark:focus:ring-blue-400"
            aria-label="Search transcripts"
            autoComplete="off"
          />
          {q && (
            <button
              type="button"
              onClick={clearSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300"
              aria-label="Clear search"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value as 'native' | 'youtube')}
          className="rounded-md border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 px-3 py-3 text-sm focus:border-blue-600 dark:focus:border-blue-400 focus:ring-2 focus:ring-blue-600 dark:focus:ring-blue-400"
          aria-label="Select transcript source"
        >
          <option value="native">Our Transcript</option>
          <option value="youtube">YouTube Auto-Captions</option>
        </select>
        <button 
          className="btn" 
          disabled={!q || loading}
          aria-label={loading ? 'Searching...' : 'Search'}
        >
          {loading ? (
            <>
              <span className="inline-block animate-spin mr-2" aria-hidden="true">⟳</span>
              Searching…
            </>
          ) : (
            'Search'
          )}
        </button>
      </form>

      {!q && (
        <div className="text-center py-12">
          <svg className="w-16 h-16 mx-auto mb-4 text-stone-300 dark:text-stone-700" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <p className="text-stone-500 dark:text-stone-400 text-lg">Enter a query to search.</p>
        </div>
      )}

      {q && loading && (
        <div className="text-center py-12" role="status" aria-live="polite">
          <div className="inline-block animate-spin text-4xl mb-4" aria-hidden="true">⟳</div>
          <p className="text-stone-500 dark:text-stone-400 text-lg">Searching…</p>
        </div>
      )}

      {q && !loading && (
        <div className="space-y-6">
          {quotaError && (
            <div className="rounded-md border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 p-4 text-amber-800 dark:text-amber-200" role="alert">
              <div className="mb-2 font-medium">Daily search limit reached</div>
              <div className="text-sm">
                You used {quotaError.used}/{quotaError.limit} searches today. Upgrade to Pro for
                unlimited search and exports.
              </div>
              <Link to="/pricing" className="mt-2 inline-block text-blue-600 dark:text-blue-400 hover:underline">
                See pricing
              </Link>
            </div>
          )}
          
          {grouped.length === 0 && !quotaError && (
            <div className="text-center py-12">
              <svg className="w-16 h-16 mx-auto mb-4 text-stone-300 dark:text-stone-700" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M12 12h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-stone-500 dark:text-stone-400 text-lg">No results found for "{q}"</p>
              <p className="text-stone-400 dark:text-stone-500 text-sm mt-2">Try different keywords or check your spelling</p>
            </div>
          )}

          {grouped.map(([videoId, group]) => (
            <article key={videoId} className="rounded-lg border border-stone-200 dark:border-stone-800 p-4 sm:p-6 bg-white dark:bg-stone-900">
              <div className="mb-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <Link to={`/v/${videoId}`} className="font-semibold text-lg hover:underline focus:underline">
                  Video {videoId.slice(0, 8)}…
                </Link>
                <span className="text-sm text-stone-500 dark:text-stone-400">{group.length} {group.length === 1 ? 'match' : 'matches'}</span>
              </div>
              <ul className="space-y-3" role="list">
                {group.slice(0, 5).map((h) => (
                  <li key={h.id} className="rounded-md border border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-800 p-3 sm:p-4">
                    <div className="mb-2 text-sm text-stone-600 dark:text-stone-400">
                      <time dateTime={`PT${Math.floor(h.start_ms / 1000)}S`}>
                        {msToTimestamp(h.start_ms)}–{msToTimestamp(h.end_ms)}
                      </time>
                      {' • '}
                      <span>{source === 'native' ? 'Our Transcript' : 'YouTube'}</span>
                    </div>
                    <div
                      className="prose prose-sm dark:prose-invert max-w-none"
                      dangerouslySetInnerHTML={{ __html: h.snippet }}
                    />
                    <div className="mt-3 flex flex-wrap gap-3 text-sm">
                      <Link
                        to={`/v/${videoId}?t=${Math.floor(h.start_ms / 1000)}#seg-${h.id}`}
                        className="text-blue-600 dark:text-blue-400 hover:underline focus:underline"
                        onClick={() =>
                          track({
                            type: 'result_click',
                            payload: { videoId, start_ms: h.start_ms, id: h.id, source },
                          })
                        }
                      >
                        Open at timestamp
                      </Link>
                      <button
                        type="button"
                        onClick={() => {
                          const deep = `${location.origin}/v/${videoId}?t=${Math.floor(h.start_ms / 1000)}#seg-${h.id}`;
                          navigator.clipboard?.writeText(deep);
                        }}
                        className="text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-100"
                        aria-label="Copy link to this segment"
                        title="Copy link"
                      >
                        Copy link
                      </button>
                    </div>
                  </li>
                ))}
                {group.length > 5 && (
                  <li>
                    <Link
                      to={`/v/${videoId}?q=${encodeURIComponent(q)}`}
                      className="text-blue-600 dark:text-blue-400 hover:underline focus:underline"
                    >
                      Show {group.length - 5} more {group.length - 5 === 1 ? 'hit' : 'hits'} in this video
                    </Link>
                  </li>
                )}
              </ul>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
