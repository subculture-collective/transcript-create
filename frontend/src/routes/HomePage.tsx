import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, useAuth } from '../services';
import type { ArchiveSummary } from '../types/api';
import {
  buildTimestampLink,
  formatDate,
  formatDuration,
  formatNumber,
} from '../features/archive/format';
import { VideoCard } from '../components/archive';

const searchExamples = ['labor', 'Gaza', 'housing', 'election'];

export default function HomePage() {
  const navigate = useNavigate();
  const { user, loading: authLoading, login, loginTwitch } = useAuth();
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
  const newestVideo = recentVideos[0];

  return (
    <div className="space-y-5 lg:space-y-7">
      <section className="archive-masthead">
        <div className="relative z-10 grid min-h-[34rem] gap-10 px-5 py-8 sm:px-8 sm:py-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(24rem,0.85fr)] lg:items-end lg:px-12 lg:py-14">
          <div className="space-y-8">
            <div className="flex flex-wrap items-center gap-2">
              <span className="archive-eyebrow">HasanAbi broadcast archive</span>
              <span className="source-pill">searchable transcripts</span>
            </div>

            <div className="space-y-6">
              <h1 className="archive-display">Find the moment. Read the record.</h1>
              <p className="max-w-2xl text-lg leading-8 text-muted sm:text-xl">
                Search years of broadcasts by topic or exact phrase, then move from the result
                straight into the cited transcript and VOD.
              </p>
            </div>

            <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
              <Link to="/explore" className="action-link font-semibold">
                Explore the archive →
              </Link>
              <Link to="/episodes" className="text-muted transition-colors hover:text-ink">
                Browse every VOD
              </Link>
            </div>
          </div>

          <div className="space-y-4 lg:pb-1">
            <div className="archive-rule-title">Search the record</div>
            <form onSubmit={onSubmit} className="archive-command">
              <label className="sr-only" htmlFor="home-search">
                Search the HasanAbi archive
              </label>
              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                <div className="flex min-w-0 items-center gap-3 px-3">
                  <svg
                    className="h-5 w-5 shrink-0 text-subtle"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    aria-hidden="true"
                  >
                    <circle cx="11" cy="11" r="7" strokeWidth="1.8" />
                    <path d="m20 20-4-4" strokeWidth="1.8" strokeLinecap="round" />
                  </svg>
                  <input
                    id="home-search"
                    name="q"
                    type="search"
                    autoComplete="off"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="A topic, quote, guest, or phrase…"
                    className="min-h-[54px] w-full bg-transparent text-lg text-ink outline-none placeholder:text-subtle"
                  />
                </div>
                <button type="submit" className="btn min-h-[54px] px-7">
                  Search archive
                </button>
              </div>
            </form>

            <div className="flex flex-wrap items-center gap-2 text-xs text-subtle">
              <span className="mr-1 uppercase tracking-[0.18em]">Try</span>
              {searchExamples.map((term) => (
                <Link
                  key={term}
                  to={`/search?q=${encodeURIComponent(term)}`}
                  className="source-pill hover:border-accent/50 hover:text-ink"
                >
                  {term}
                </Link>
              ))}
            </div>
          </div>
        </div>

        <div className="archive-data-strip relative z-10">
          <div className="archive-data-cell">
            <div className="meta-label">Archived VODs</div>
            <div className="mt-2 font-mono text-xl font-semibold text-ink">
              {loading ? '—' : summary ? formatNumber(summary.video_count) : '—'}
            </div>
          </div>
          <div className="archive-data-cell">
            <div className="meta-label">Recorded runtime</div>
            <div className="mt-2 font-mono text-xl font-semibold text-ink">
              {loading ? '—' : summary ? formatDuration(summary.total_duration_seconds) : '—'}
            </div>
          </div>
          <div className="archive-data-cell">
            <div className="meta-label">Transcript words</div>
            <div className="mt-2 font-mono text-xl font-semibold text-ink">
              {loading ? '—' : summary ? formatNumber(summary.transcript_word_count) : '—'}
            </div>
          </div>
          <div className="archive-data-cell">
            <div className="meta-label">Index refreshed</div>
            <div className="mt-2 font-mono text-sm font-semibold text-ink">
              {loading ? 'Checking…' : formatDate(summary?.updated_at ?? null)}
            </div>
          </div>
        </div>
      </section>

      <section className="archive-section">
        {!authLoading && !user ? (
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
            <div>
              <div className="archive-eyebrow">Save your archive trail</div>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-ink">
                Sign in to synchronize saved moments and searches.
              </h2>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={login} className="btn min-h-11 px-4 text-sm">
                Continue with Google
              </button>
              <button
                type="button"
                onClick={loginTwitch}
                className="btn-secondary min-h-11 px-4 text-sm"
              >
                Continue with Twitch
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="archive-eyebrow">Archive trail</div>
              <p className="mt-2 font-semibold text-ink">
                {authLoading ? 'Checking your account…' : 'Your saves are synchronized.'}
              </p>
            </div>
            {!authLoading && (
              <Link to="/saved" className="btn-secondary min-h-11 px-4 text-sm">
                Open my saves
              </Link>
            )}
          </div>
        )}
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="archive-section space-y-5">
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="archive-eyebrow">Latest signal</div>
              <h2 className="mt-3 text-3xl font-semibold tracking-[-0.045em] text-ink">
                Recently indexed
              </h2>
            </div>
            <Link to="/episodes" className="action-link text-sm">
              All VODs →
            </Link>
          </div>

          {recentVideos.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {recentVideos.slice(0, 6).map((video) => (
                <VideoCard key={video.id} video={video} />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted">
              {loading
                ? 'Loading recent VODs…'
                : 'Recent VODs will appear when the archive summary is available.'}
            </div>
          )}
        </div>

        <aside className="archive-section flex flex-col gap-6">
          <div>
            <div className="archive-eyebrow">Open a thread</div>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-ink">
              Popular searches
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              Recurring archive terms, ready to open as timestamped evidence.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {suggested.length > 0 ? (
              suggested.slice(0, 12).map((item, index) => (
                <Link
                  key={item.term}
                  to={`/search?q=${encodeURIComponent(item.term)}`}
                  className="group inline-flex items-center gap-2 rounded-lg border border-border bg-surface-muted px-3 py-2 text-sm text-ink transition-colors hover:border-accent/60"
                >
                  <span className="translate-y-px font-mono text-[10px] text-subtle">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="group-hover:text-accent">{item.term}</span>
                </Link>
              ))
            ) : (
              <p className="text-sm text-muted">
                Search activity will surface useful starting points here.
              </p>
            )}
          </div>

          {newestVideo && (
            <Link
              to={buildTimestampLink(newestVideo.id, 0)}
              className="mt-auto rounded-xl border border-accent/20 bg-accent-soft/55 p-4 transition-colors hover:border-accent/50"
            >
              <div className="meta-label text-accent">Newest transcript</div>
              <div className="mt-2 line-clamp-2 font-semibold text-ink">
                {newestVideo.title || 'Open the newest VOD'}
              </div>
              <div className="mt-3 text-sm text-accent">Start reading →</div>
            </Link>
          )}
        </aside>
      </section>

      <section className="archive-section grid gap-6 lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1.25fr)] lg:items-center">
        <div>
          <div className="archive-eyebrow">How it works</div>
          <h2 className="mt-3 text-3xl font-semibold tracking-[-0.045em] text-ink">
            From broadcast to evidence.
          </h2>
        </div>
        <ol className="grid gap-3 sm:grid-cols-3">
          {[
            ['01', 'Search', 'Use a subject, name, or exact phrase.'],
            ['02', 'Inspect', 'Compare matching moments across VODs.'],
            ['03', 'Read', 'Open the transcript at the cited timestamp.'],
          ].map(([number, title, copy]) => (
            <li key={number} className="border-l border-border pl-4">
              <div className="font-mono text-xs text-accent">{number}</div>
              <div className="mt-2 font-semibold text-ink">{title}</div>
              <p className="mt-1 text-sm leading-6 text-muted">{copy}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
