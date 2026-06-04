import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, useAuth } from '../services';
import type { ArchiveSummary } from '../types/api';
import { buildTimestampLink, formatDate, formatDuration, formatNumber } from '../features/archive/format';
import { StatCard, VideoCard } from '../components/archive';

export default function HomePage() {
  const navigate = useNavigate();
  const { login, loginTwitch } = useAuth();
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
      <section className="surface-card space-y-7 overflow-hidden">
        <div className="flex flex-col justify-between gap-7 lg:flex-row lg:items-end">
          <div className="max-w-3xl space-y-4">
            <div className="archive-eyebrow">HasAnAra</div>
            <h1 className="page-title max-w-4xl">Search the HasanAbi broadcast archive.</h1>
            <p className="max-w-2xl text-lg leading-8 text-muted">
              Trace topics, timestamped quotes, debates, guests, and recurring stream moments across HasanAbi VODs.
            </p>
          </div>

          <div className="w-full max-w-2xl space-y-4 lg:min-w-[28rem]">
            <form onSubmit={onSubmit} className="space-y-3">
              <label className="sr-only" htmlFor="home-search">
                Search the HasanAbi archive
              </label>
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
                <input
                  id="home-search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search any topic, line, guest, or phrase…"
                  className="form-control min-h-[52px] px-4 text-base tracking-[-0.02em] placeholder:text-subtle"
                />
                <button type="submit" className="btn min-h-[52px] px-6 text-base">
                  Search archive
                </button>
              </div>

              <div className="flex flex-wrap gap-2 text-sm text-muted">
                <span className="source-pill">timestamped results</span>
                <span className="source-pill">VOD dossiers</span>
                <span className="match-pill">highlighted matches</span>
              </div>
            </form>

            <div className="flex flex-wrap justify-start gap-3 text-sm lg:justify-end">
              <Link to="/episodes" className="nav-link">
                Browse VODs
              </Link>
              <Link to="/saved" className="nav-link">
                Saved moments
              </Link>
            </div>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,0.7fr)] lg:items-stretch">
          <div className="archive-panel grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <StatCard label="VODs" value={loading ? '—' : summary ? formatNumber(summary.video_count) : '—'} />
              <StatCard label="Duration" value={loading ? '—' : summary ? formatDuration(summary.total_duration_seconds) : '—'} />
              <StatCard label="Transcript words" value={loading ? '—' : summary ? formatNumber(summary.transcript_word_count) : '—'} />
              <StatCard
                label="Updated"
                value={loading ? 'Loading…' : formatDate(summary?.updated_at ?? null)}
                className="sm:col-span-1"
                valueClassName="meta-value text-sm"
              />
          </div>

          <div className="rounded-2xl border border-border bg-surface p-4 shadow-sm">
              <div className="archive-eyebrow mb-2">Get started</div>
              <h2 className="text-xl font-semibold tracking-[-0.03em] text-ink">Create an account to save searches and favorites.</h2>
              <p className="mt-2 text-sm leading-6 text-muted">
                Use your existing Google or Twitch login to keep your archive trail in sync.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" onClick={login} className="btn min-h-[44px] px-4 text-sm">
                  Continue with Google
                </button>
                <button type="button" onClick={loginTwitch} className="btn-secondary min-h-[44px] px-4 text-sm">
                  Continue with Twitch
                </button>
              </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)]">
        <div className="surface-card space-y-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="archive-eyebrow mb-2">Latest signal</div>
              <h2 className="section-title">Recent VODs</h2>
            </div>
            <Link to="/episodes" className="action-link text-sm">
              View all
            </Link>
          </div>

          {recentVideos.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2">
              {recentVideos.map((video) => (
                <VideoCard key={video.id} video={video} />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border p-6 text-sm text-muted">
              Recent VODs will appear here once the archive summary endpoint is available.
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
            <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted">
              Search a topic above to start building a useful archive trail.
            </div>
          )}

          {recentVideos[0] && (
            <Link
              to={buildTimestampLink(recentVideos[0].id, 0)}
              className="block rounded-lg border border-border bg-surface-muted p-4 text-sm text-muted transition-colors hover:border-accent/70 hover:text-ink"
            >
              Open the newest VOD in the player.
            </Link>
          )}
        </aside>
      </section>
    </div>
  );
}
