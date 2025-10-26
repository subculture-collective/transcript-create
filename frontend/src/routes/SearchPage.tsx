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

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next = new URLSearchParams(params);
    if (q) next.set('q', q);
    else next.delete('q');
    setParams(next);
  }

  return (
    <div className="space-y-6">
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search transcripts…"
          className="w-full rounded-md border px-3 py-2"
        />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value as 'native' | 'youtube')}
          className="rounded-md border px-2 py-2 text-sm"
        >
          <option value="native">Our Transcript</option>
          <option value="youtube">YouTube Auto-Captions</option>
        </select>
        <button className="btn" disabled={!q || loading}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {!q && <p className="text-gray-500">Enter a query to search.</p>}
      {q && loading && <p className="text-gray-500">Searching…</p>}

      {q && !loading && (
        <div className="space-y-6">
          {quotaError && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-800">
              <div className="mb-2 font-medium">Daily search limit reached</div>
              <div className="text-sm">
                You used {quotaError.used}/{quotaError.limit} searches today. Upgrade to Pro for
                unlimited search and exports.
              </div>
              <Link to="/pricing" className="mt-2 inline-block text-blue-600 hover:underline">
                See pricing
              </Link>
            </div>
          )}
          {grouped.map(([videoId, group]) => (
            <div key={videoId} className="rounded-lg border p-4">
              <div className="mb-2 flex items-center justify-between">
                <Link to={`/v/${videoId}`} className="font-semibold hover:underline">
                  Video {videoId.slice(0, 8)}…
                </Link>
              </div>
              <ul className="space-y-3">
                {group.slice(0, 5).map((h) => (
                  <li key={h.id} className="rounded-md border bg-gray-50 p-3">
                    <div className="mb-1 text-sm text-gray-600">
                      {msToTimestamp(h.start_ms)}–{msToTimestamp(h.end_ms)} •{' '}
                      {source === 'native' ? 'Our Transcript' : 'YouTube'}
                    </div>
                    <div
                      className="prose prose-sm max-w-none"
                      dangerouslySetInnerHTML={{ __html: h.snippet }}
                    />
                    <div className="mt-2 text-sm">
                      <Link
                        to={`/v/${videoId}?t=${Math.floor(h.start_ms / 1000)}#seg-${h.id}`}
                        className="text-blue-600 hover:underline"
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
                        className="ml-3 text-gray-600 hover:text-gray-900"
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
                      className="text-blue-600 hover:underline"
                    >
                      Show {group.length - 5} more hits in this video
                    </Link>
                  </li>
                )}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
