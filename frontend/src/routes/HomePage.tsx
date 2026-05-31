import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../services';
import type { ArchiveSummary } from '../types/api';
import { buildTimestampLink, formatDate, formatDuration, formatNumber } from '../features/archive/format';

export default function HomePage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<ArchiveSummary | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getArchiveSummary()
      .then(setSummary)
      .catch((err: unknown) => {
        console.error('Failed to load archive summary', err);
        setSummary(null);
      })
      .finally(() => setLoading(false));
  }, []);

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    navigate(`/search?q=${encodeURIComponent(trimmed)}`);
  }

  const recentVideos = summary?.recent_videos ?? [];
  const suggested = summary?.popular_searches ?? [];

  return (
    <div className="space-y-6 lg:space-y-8">
      <section className="surface-card overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(183,255,60,0.12),transparent_22%),radial-gradient(circle_at_20%_15%,rgba(192,132,252,0.10),transparent_18%)]" />
        <div className="relative grid gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(19rem,0.8fr)] lg:items-end">
          <div className="space-y-6">
            <div className="archive-eyebrow">Broadcast archive noir</div>

            <div className="space-y-4">
              <h1 className="page-title max-w-4xl">Search the archive like a dossier, not a dashboard.</h1>
              <p className="max-w-2xl text-lg leading-8 text-muted">
                Trace topics, timestamped quotes, and episode fragments across the full archive with a search interface that feels like a broadcast control room.
              </p>
            </div>

            <form onSubmit={onSubmit} className="space-y-3">
              <label className="sr-only" htmlFor="home-search">
                Search the archive
              </label>
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
                <input
                  id="home-search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search any topic, line, guest, or phrase…"
                  className="form-control min-h-[64px] rounded-[1.5rem] px-5 text-lg tracking-[-0.02em] placeholder:text-subtle"
                />
                <button type="submit" className="btn min-h-[64px] px-7 text-base">
                  Search archive
                </button>
              </div>

              <div className="flex flex-wrap gap-2 text-sm text-muted">
                <span className="source-pill">timestamped results</span>
                <span className="source-pill">episode dossiers</span>
                <span className="match-pill">highlighted matches</span>
              </div>
            </form>

            <div className="flex flex-wrap gap-3 text-sm">
              <Link to="/episodes" className="nav-link">
                Browse episodes
              </Link>
              <Link to="/timeline" className="nav-link">
                Timeline
              </Link>
              <Link to="/saved" className="nav-link">
                Saved moments
              </Link>
            </div>
          </div>

          <div className="archive-panel grid grid-cols-2 gap-3 text-sm sm:grid-cols-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-border/80 bg-surface-muted/70 p-4">
              <div className="meta-label">Episodes</div>
              <div className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-ink">
                {loading ? '—' : summary ? formatNumber(summary.video_count) : '—'}
              </div>
            </div>
            <div className="rounded-2xl border border-border/80 bg-surface-muted/70 p-4">
              <div className="meta-label">Duration</div>
              <div className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-ink">
                {loading ? '—' : summary ? formatDuration(summary.total_duration_seconds) : '—'}
              </div>
            </div>
            <div className="rounded-2xl border border-border/80 bg-surface-muted/70 p-4">
              <div className="meta-label">Transcript words</div>
              <div className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-ink">
                {loading ? '—' : summary ? formatNumber(summary.transcript_word_count) : '—'}
              </div>
            </div>
            <div className="rounded-2xl border border-border/80 bg-surface-muted/70 p-4 sm:col-span-2 lg:col-span-2">
              <div className="meta-label">Updated</div>
              <div className="meta-value text-sm">{loading ? 'Loading…' : formatDate(summary?.updated_at ?? null)}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)]">
        <div className="surface-card space-y-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="archive-eyebrow mb-2">Latest signal</div>
              <h2 className="section-title">Recent episodes</h2>
            </div>
            <Link to="/episodes" className="action-link text-sm">
              View all
            </Link>
          </div>

          {recentVideos.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2">
              {recentVideos.map((video) => (
                <Link
                  key={video.id}
                  to={`/v/${video.id}`}
                  className="surface-card-compact block border-border/80 transition-all hover:-translate-y-0.5 hover:border-accent/70 hover:shadow-[0_18px_35px_rgba(0,0,0,0.25)]"
                >
                  <div className="line-clamp-2 font-semibold tracking-[-0.03em] text-ink">{video.title || 'Untitled episode'}</div>
                  <div className="mt-2 text-sm text-muted">{video.channel_name || 'Unknown channel'}</div>
                  <div className="mt-4 flex flex-wrap gap-2 text-xs">
                    <span className="timestamp-pill">{formatDuration(video.duration_seconds)}</span>
                    <span className="source-pill">{formatDate(video.uploaded_at ?? video.created_at ?? null)}</span>
                    <span className="match-pill">{video.has_whisper_transcript ? 'whisper ready' : 'pending transcript'}</span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-border p-6 text-sm text-muted">
              Recent episodes will appear here once the archive summary endpoint is available.
            </div>
          )}
        </div>

        <aside className="surface-card space-y-5">
          <div>
            <div className="archive-eyebrow mb-2">Popular signal</div>
            <h2 className="section-title">Suggested searches</h2>
            <p className="mt-2 text-sm text-muted">Real archive terms with fast jump links into the search engine.</p>
          </div>

          {suggested.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {suggested.map((item) => (
                <Link key={item.term} to={`/search?q=${encodeURIComponent(item.term)}`} className="badge-warning">
                  {item.term}
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-border p-4 text-sm text-muted">
              Search a topic above to start building a useful archive trail.
            </div>
          )}

          {recentVideos[0] && (
            <Link
              to={buildTimestampLink(recentVideos[0].id, 0)}
              className="block rounded-2xl border border-border bg-surface-muted p-4 text-sm text-muted transition-colors hover:border-accent/70 hover:text-ink"
            >
              Open the newest episode in the player.
            </Link>
          )}
        </aside>
      </section>
    </div>
  );
}
