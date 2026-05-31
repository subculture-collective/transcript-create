import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, apiAddFavorite, favorites, track, useAuth } from '../services';
import type { GroupedSearchResponse, MentionMapResponse, SearchHit } from '../types/api';
import { buildTimestampLink, formatDate, formatDuration, formatNumber, formatTimestamp, sourceLabel } from '../features/archive/format';

function mentionLink(videoId: string, moment: SearchHit) {
  return buildTimestampLink(videoId, moment.start_ms, moment.id);
}

function plainTextFromSnippet(snippet: string) {
  return snippet.replace(/<mark>/gi, '').replace(/<\/mark>/gi, '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

function copyText(text: string) {
  void navigator.clipboard?.writeText(text);
}

function quoteText(videoId: string, moment: SearchHit, title: string) {
  const url = `${window.location.origin}${buildTimestampLink(videoId, moment.start_ms, moment.id)}`;
  return `“${plainTextFromSnippet(moment.snippet)}”\n\n— ${title}, ${formatTimestamp(moment.start_ms)}\n${url}`;
}

function buildPlayMatchesLink(videoId: string, moment: SearchHit, query: string) {
  const params = new URLSearchParams({ t: String(Math.floor(moment.start_ms / 1000)), q: query, play: 'matches' });
  return `/v/${videoId}?${params.toString()}#seg-${moment.id}`;
}

export default function TopicPage() {
  const { query } = useParams();
  const topic = query ?? '';
  const [mentionMap, setMentionMap] = useState<MentionMapResponse | null>(null);
  const [grouped, setGrouped] = useState<GroupedSearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());
  const { user } = useAuth();

  useEffect(() => {
    if (!topic) return;
    setLoading(true);
    api
      .getMentionMap(topic)
      .then((map) => {
        setMentionMap(map);
        setGrouped({
          total_moments: map.total_moments,
          total_videos: map.total_videos,
          groups: map.top_episodes,
          query_time_ms: map.query_time_ms,
        });
        setError(null);
      })
      .catch((err: unknown) => {
        console.error('Failed to load topic page', err);
        setMentionMap(null);
        setGrouped(null);
        setError('Topic page failed to load.');
      })
      .finally(() => setLoading(false));
  }, [topic]);

  const topEpisodes = mentionMap?.top_episodes ?? [];

  async function saveMoment(videoId: string, moment: SearchHit) {
    const key = `${videoId}:${moment.start_ms}:${moment.end_ms}`;
    try {
      const text = plainTextFromSnippet(moment.snippet);
      if (user) {
        await apiAddFavorite({ video_id: videoId, start_ms: moment.start_ms, end_ms: moment.end_ms, text });
      } else {
        favorites.toggle({ videoId, segIndex: moment.id, startMs: moment.start_ms, endMs: moment.end_ms, text });
      }
      setSavedKeys((current) => new Set([...current, key]));
      track({ type: 'favorite_add', payload: { videoId, start_ms: moment.start_ms, topic } });
    } catch (err) {
      console.error('Failed to save topic moment', err);
      setError('Could not save that moment.');
    }
  }

  if (!topic) {
    return <div className="surface-card text-muted">Pick a topic from search results first.</div>;
  }

  return (
    <div className="space-y-6">
      <section className="surface-card space-y-4">
        <div>
          <div className="text-xs uppercase tracking-[0.24em] text-subtle">Topic</div>
          <h1 className="page-title mt-2">Topic: {topic}</h1>
          <p className="mt-2 max-w-2xl text-muted">
            Citation-backed mention map for a real search term. This page only shows moments that were actually found in the archive.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-border bg-surface-muted p-4">
            <div className="text-xs uppercase tracking-wide text-subtle">Query</div>
            <div className="mt-1 text-2xl font-semibold text-ink">“{mentionMap?.query ?? topic}”</div>
          </div>
          <div className="rounded-xl border border-border bg-surface-muted p-4">
            <div className="text-xs uppercase tracking-wide text-subtle">First mentioned</div>
            <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : mentionMap?.first_mentioned_year ?? '—'}</div>
          </div>
          <div className="rounded-xl border border-border bg-surface-muted p-4">
            <div className="text-xs uppercase tracking-wide text-subtle">Most discussed</div>
            <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : mentionMap?.most_discussed_period ?? '—'}</div>
            {!loading && mentionMap?.most_discussed_count ? <div className="mt-1 text-xs text-muted">{formatNumber(mentionMap.most_discussed_count)} moments</div> : null}
          </div>
          <div className="rounded-xl border border-border bg-surface-muted p-4">
            <div className="text-xs uppercase tracking-wide text-subtle">Recent mentions</div>
            <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : formatNumber(mentionMap?.recent_mentions_90d ?? 0)}</div>
            <div className="mt-1 text-xs text-muted">last 90 days</div>
          </div>
          <div className="rounded-xl border border-border bg-surface-muted p-4">
            <div className="text-xs uppercase tracking-wide text-subtle">Related topics</div>
            <div className="mt-2 flex flex-wrap gap-2 text-sm text-ink">
              {(mentionMap?.related_topics ?? []).length > 0 ? mentionMap!.related_topics!.map((term) => (
                <Link key={term} to={`/topics/${encodeURIComponent(term)}`} className="rounded-full border border-border bg-surface px-2 py-1 hover:border-accent">
                  {term}
                </Link>
              )) : <span className="text-muted">No co-occurring terms yet</span>}
            </div>
          </div>
          <div className="rounded-xl border border-border bg-surface-muted p-4">
            <div className="text-xs uppercase tracking-wide text-subtle">Top episodes</div>
            <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : formatNumber(mentionMap?.top_episodes_count ?? topEpisodes.length)}</div>
          </div>
          <div className="rounded-xl border border-border bg-surface-muted p-4">
            <div className="text-xs uppercase tracking-wide text-subtle">Total moments</div>
            <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : formatNumber(mentionMap?.total_moments)}</div>
          </div>
          <div className="rounded-xl border border-border bg-surface-muted p-4">
            <div className="text-xs uppercase tracking-wide text-subtle">Episodes</div>
            <div className="mt-1 text-2xl font-semibold text-ink">{loading ? '—' : formatNumber(mentionMap?.total_videos)}</div>
          </div>
        </div>
      </section>

      {error && <div className="alert-warning" role="alert">{error}</div>}

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="surface-card space-y-4">
          <h2 className="section-title">First and latest mentions</h2>
          <div className="space-y-3">
            {mentionMap?.first_mention ? (
              <MentionCard label="First mention" moment={mentionMap.first_mention} />
            ) : (
              <EmptyState label="First mention" />
            )}
            {mentionMap?.latest_mention ? (
              <MentionCard label="Latest mention" moment={mentionMap.latest_mention} />
            ) : (
              <EmptyState label="Latest mention" />
            )}
          </div>
        </div>

        <div className="surface-card space-y-4">
          <h2 className="section-title">Top episodes</h2>
          <div className="space-y-3">
            {topEpisodes.length > 0 ? (
              topEpisodes.map((entry) => (
                <div key={entry.video.id} className="rounded-xl border border-border bg-surface-muted p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <Link to={`/v/${entry.video.id}`} className="font-semibold text-ink hover:text-accent">
                        {entry.video.title || 'Untitled episode'}
                      </Link>
                      <div className="mt-1 text-sm text-muted">
                        {entry.video.channel_name || 'Unknown channel'} · {formatDate(entry.video.uploaded_at ?? null)}
                      </div>
                    </div>
                    <div className="text-sm text-muted">{formatNumber(entry.moments.length)} mentions</div>
                  </div>
                  <div className="mt-3 text-xs uppercase tracking-wide text-subtle">Duration {formatDuration(entry.video.duration_seconds)}</div>
                  {entry.moments[0] && (
                    <Link to={buildPlayMatchesLink(entry.video.id, entry.moments[0] as SearchHit, topic)} className="action-link mt-3 inline-block">
                      Play all matches
                    </Link>
                  )}
                  <div className="mt-3 text-sm text-muted">
                    {entry.moments[0] && (
                      <div>
                        First: <Link className="action-link" to={mentionLink(entry.video.id, entry.moments[0])}>{formatTimestamp(entry.moments[0].start_ms)}</Link>
                      </div>
                    )}
                    {entry.moments.at(-1) && (
                      <div>
                        Latest: <Link className="action-link" to={mentionLink(entry.video.id, entry.moments.at(-1)!)}>{formatTimestamp(entry.moments.at(-1)!.start_ms)}</Link>
                      </div>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <EmptyState label="Top episodes" />
            )}
          </div>
        </div>
      </section>

      <section className="surface-card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="section-title">Grouped results</h2>
          <Link to={`/search?q=${encodeURIComponent(topic)}`} className="action-link">
            Open search
          </Link>
        </div>
        {grouped?.groups?.length ? (
          <div className="space-y-4">
            {grouped.groups.map((group) => (
              <div key={group.video.id} className="rounded-xl border border-border bg-surface-muted p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <Link to={`/v/${group.video.id}`} className="font-semibold text-ink hover:text-accent">
                      {group.video.title || 'Untitled episode'}
                    </Link>
                    <div className="mt-1 text-sm text-muted">{group.video.channel_name || 'Unknown channel'}</div>
                  </div>
                  <div className="text-sm text-muted">{group.moments.length} moments</div>
                </div>
                <div className="mt-3 space-y-2">
                  {group.moments.map((moment) => (
                    <div key={moment.id} className="rounded-lg border border-border bg-surface p-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-subtle">
                        <span>{formatTimestamp(moment.start_ms)}</span>
                        <span>{sourceLabel(moment.source ?? 'best')}</span>
                      </div>
                      <div className="prose prose-sm mt-2 max-w-none dark:prose-invert" dangerouslySetInnerHTML={{ __html: moment.snippet }} />
                      <div className="mt-3 flex flex-wrap gap-3 text-sm">
                        <Link className="action-link" to={mentionLink(group.video.id, moment as SearchHit)}>Open cited moment</Link>
                        <button type="button" className="nav-link" onClick={() => copyText(quoteText(group.video.id, moment as SearchHit, group.video.title || 'Untitled episode'))}>Copy quote</button>
                        <button
                          type="button"
                          className="nav-link"
                          disabled={savedKeys.has(`${group.video.id}:${moment.start_ms}:${moment.end_ms}`)}
                          onClick={() => saveMoment(group.video.id, moment as SearchHit)}
                        >
                          {savedKeys.has(`${group.video.id}:${moment.start_ms}:${moment.end_ms}`) ? 'Saved moment' : 'Save moment'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-muted">{loading ? 'Loading moments…' : 'No grouped results.'}</div>
        )}
      </section>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="rounded-xl border border-dashed border-border p-4 text-sm text-muted">No {label.toLowerCase()} yet.</div>;
}

function MentionCard({ label, moment }: { label: string; moment: SearchHit & { video?: { id?: string } | null } }) {
  const videoId = moment.video?.id ?? moment.video_id;
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="text-xs uppercase tracking-wide text-subtle">{label}</div>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
        <span>{formatTimestamp(moment.start_ms)}</span>
        <span>{sourceLabel(moment.source ?? 'best')}</span>
        {videoId && <Link className="action-link" to={buildTimestampLink(videoId, moment.start_ms, moment.id)}>Open cited moment</Link>}
      </div>
      <div className="prose prose-sm mt-3 max-w-none dark:prose-invert" dangerouslySetInnerHTML={{ __html: moment.snippet }} />
    </div>
  );
}
