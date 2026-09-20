import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiAddFavorite, favorites, track, useAuth } from '../services';
import type { GroupedSearchResponse, MentionMapResponse, SearchHit } from '../types/api';
import {
  buildTimestampLink,
  formatDate,
  formatDuration,
  formatNumber,
  formatTimestamp,
} from '../features/archive/format';
import {
  OpinionHistory,
  TopicMentionCard,
  TopicStatsGrid,
  TopicTimeline,
} from '../components/archive';
import type { OpinionHistoryItem } from '../types/api';
import HighlightedSnippet from '../components/HighlightedSnippet';
import { buildPlayMatchesLink, plainTextFromSnippet } from '../features/search/moments';

function mentionLink(videoId: string, moment: SearchHit) {
  return buildTimestampLink(videoId, moment.start_ms, moment.source);
}

async function copyText(text: string) {
  if (!navigator.clipboard) throw new Error('Clipboard unavailable');
  await navigator.clipboard.writeText(text);
}

function quoteText(videoId: string, moment: SearchHit, title: string) {
  const url = `${window.location.origin}${buildTimestampLink(videoId, moment.start_ms, moment.source)}`;
  return `“${plainTextFromSnippet(moment.snippet, moment.highlights)}”\n\n— ${title}, ${formatTimestamp(moment.start_ms)}\n${url}`;
}

export default function TopicPage() {
  const { query } = useParams();
  const topic = query ?? '';
  const [timelineParams, setTimelineParams] = useSearchParams();
  const granularity = timelineParams.get('granularity') === 'week' ? 'week' : 'month';
  const dateFrom = timelineParams.get('date_from') ?? '';
  const dateTo = timelineParams.get('date_to') ?? '';
  const [mentionMap, setMentionMap] = useState<MentionMapResponse | null>(null);
  const [grouped, setGrouped] = useState<GroupedSearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState<string | null>(null);
  const [evidenceLimit, setEvidenceLimit] = useState(3);
  const { user, capabilities } = useAuth();
  const queryClient = useQueryClient();
  const timeline = useQuery({
    queryKey: ['topic-timeline', topic, granularity, dateFrom, dateTo],
    enabled: Boolean(topic),
    queryFn: ({ signal }) =>
      api.getTopicTimeline(
        topic,
        {
          granularity,
          ...(dateFrom ? { date_from: dateFrom } : {}),
          ...(dateTo ? { date_to: dateTo } : {}),
        },
        signal
      ),
  });
  const timelineBuckets = timeline.data?.buckets ?? [];
  const opinions = useQuery({
    queryKey: ['topic-opinions', topic],
    enabled: Boolean(topic),
    queryFn: ({ signal }) => api.getTopicOpinions(topic, signal),
  });

  async function correctOpinion(item: OpinionHistoryItem) {
    const reason = window.prompt('Correction reason');
    if (!reason) return;
    await api.correctOpinion(item.id, { reason });
    setFeedback('Opinion correction recorded as a new revision.');
    await queryClient.invalidateQueries({ queryKey: ['topic-opinions', topic] });
  }

  async function retractOpinion(item: OpinionHistoryItem) {
    const reason = window.prompt('Retraction reason');
    if (!reason) return;
    await api.retractOpinion(item.id, reason);
    setFeedback('Opinion retracted with revision history preserved.');
    await queryClient.invalidateQueries({ queryKey: ['topic-opinions', topic] });
  }

  function setTimelineParam(key: string, value: string) {
    const next = new URLSearchParams(timelineParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setTimelineParams(next);
  }

  function selectTimelinePeriod(period: string) {
    const month = period.match(/^(\d{4})-(\d{2})$/);
    if (!month) return;
    const year = Number(month[1]);
    const monthIndex = Number(month[2]);
    const end = new Date(Date.UTC(year, monthIndex, 0)).toISOString().slice(0, 10);
    const next = new URLSearchParams(timelineParams);
    next.set('date_from', `${month[1]}-${month[2]}-01`);
    next.set('date_to', end);
    setTimelineParams(next);
  }

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
      const text = plainTextFromSnippet(moment.snippet, moment.highlights);
      if (user) {
        await apiAddFavorite({
          video_id: videoId,
          start_ms: moment.start_ms,
          end_ms: moment.end_ms,
          text,
        });
      } else {
        favorites.toggle({
          videoId,
          segIndex: moment.id,
          startMs: moment.start_ms,
          endMs: moment.end_ms,
          text,
          source: moment.source,
        });
      }
      setSavedKeys((current) => new Set([...current, key]));
      setFeedback('Moment saved.');
      track({ type: 'favorite_add', payload: { videoId, start_ms: moment.start_ms } });
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
            Citation-backed mention map for a real search term. This page only shows moments that
            were actually found in recordings.
          </p>
        </div>

        <TopicStatsGrid mentionMap={mentionMap} topic={topic} loading={loading} />
      </section>

      {error && (
        <div className="alert-warning" role="alert">
          {error}
        </div>
      )}
      {feedback && (
        <div className="text-sm text-success" role="status">
          {feedback}
        </div>
      )}

      <section className="surface-card grid gap-3 sm:grid-cols-3" aria-label="Timeline range">
        <label className="text-sm text-muted">
          Granularity
          <select
            className="form-control mt-1"
            name="granularity"
            value={granularity}
            onChange={(event) => setTimelineParam('granularity', event.target.value)}
          >
            <option value="month">Month</option>
            <option value="week">Week</option>
          </select>
        </label>
        <label className="text-sm text-muted">
          From
          <input
            className="form-control mt-1"
            name="date_from"
            type="date"
            value={dateFrom}
            onChange={(event) => setTimelineParam('date_from', event.target.value)}
          />
        </label>
        <label className="text-sm text-muted">
          To
          <input
            className="form-control mt-1"
            name="date_to"
            type="date"
            value={dateTo}
            onChange={(event) => setTimelineParam('date_to', event.target.value)}
          />
        </label>
      </section>
      {timelineBuckets.length > 0 && (
        <div
          className="flex gap-2 overflow-x-auto pb-1 scrollbar-hidden"
          aria-label="Recent topic periods"
        >
          {timelineBuckets.slice(-8).map((bucket) => (
            <button
              key={bucket.period}
              type="button"
              className="btn-secondary shrink-0"
              onClick={() => selectTimelinePeriod(bucket.period)}
            >
              {bucket.label}
            </button>
          ))}
        </div>
      )}
      {timeline.isLoading && (
        <div className="surface-card text-muted" role="status">
          Loading topic timeline…
        </div>
      )}
      {timeline.isError && (
        <div className="alert-warning" role="alert">
          Topic timeline is temporarily unavailable.
        </div>
      )}
      {timeline.data && timelineBuckets.length > 0 && (
        <TopicTimeline data={{ ...timeline.data, buckets: timelineBuckets }} />
      )}
      {timeline.data && timelineBuckets.length === 0 && (
        <div className="surface-card text-muted">No mentions were found in this range.</div>
      )}
      {opinions.isError && (
        <div className="alert-warning" role="alert">
          Opinion history is temporarily unavailable.
        </div>
      )}
      {opinions.data && (
        <OpinionHistory
          items={opinions.data.items ?? []}
          canCorrect={capabilities.includes('admin:access')}
          onCorrect={(item) => void correctOpinion(item)}
          onRetract={(item) => void retractOpinion(item)}
        />
      )}

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="surface-card space-y-4">
          <h2 className="section-title">First and latest mentions</h2>
          <div className="space-y-3">
            {mentionMap?.first_mention ? (
              <TopicMentionCard label="First mention" moment={mentionMap.first_mention} />
            ) : (
              <EmptyState label="First mention" />
            )}
            {mentionMap?.latest_mention ? (
              <TopicMentionCard label="Latest mention" moment={mentionMap.latest_mention} />
            ) : (
              <EmptyState label="Latest mention" />
            )}
          </div>
        </div>

        <div className="surface-card space-y-4">
          <h2 className="section-title">Top VODs</h2>
          <div className="space-y-3">
            {topEpisodes.length > 0 ? (
              topEpisodes.map((entry) => (
                <div
                  key={entry.video.id}
                  className="rounded-xl border border-border bg-surface-muted p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <Link
                        to={`/v/${entry.video.id}`}
                        className="font-semibold text-ink hover:text-accent"
                      >
                        {entry.video.title || 'Untitled VOD'}
                      </Link>
                      <div className="mt-1 text-sm text-muted">
                        {entry.video.channel_name || 'Unknown channel'} ·{' '}
                        {formatDate(entry.video.uploaded_at ?? null)}
                      </div>
                    </div>
                    <div className="text-sm text-muted">
                      {formatNumber(entry.moments.length)} mentions
                    </div>
                  </div>
                  <div className="mt-3 text-xs uppercase tracking-wide text-subtle">
                    Duration {formatDuration(entry.video.duration_seconds)}
                  </div>
                  {entry.moments[0] && (
                    <Link
                      to={buildPlayMatchesLink(
                        entry.video.id,
                        entry.moments[0] as SearchHit,
                        topic
                      )}
                      className="action-link mt-3 inline-block"
                    >
                      Play all matches
                    </Link>
                  )}
                  <div className="mt-3 text-sm text-muted">
                    {entry.moments[0] && (
                      <div>
                        First:{' '}
                        <Link
                          className="action-link"
                          to={mentionLink(entry.video.id, entry.moments[0])}
                        >
                          {formatTimestamp(entry.moments[0].start_ms)}
                        </Link>
                      </div>
                    )}
                    {entry.moments.at(-1) && (
                      <div>
                        Latest:{' '}
                        <Link
                          className="action-link"
                          to={mentionLink(entry.video.id, entry.moments.at(-1)!)}
                        >
                          {formatTimestamp(entry.moments.at(-1)!.start_ms)}
                        </Link>
                      </div>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <EmptyState label="Top VODs" />
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
            {grouped.groups.slice(0, evidenceLimit).map((group) => (
              <div
                key={group.video.id}
                className="rounded-xl border border-border bg-surface-muted p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <Link
                      to={`/v/${group.video.id}`}
                      className="font-semibold text-ink hover:text-accent"
                    >
                      {group.video.title || 'Untitled VOD'}
                    </Link>
                    <div className="mt-1 text-sm text-muted">
                      {group.video.channel_name || 'Unknown channel'}
                    </div>
                  </div>
                  <div className="text-sm text-muted">{group.moments.length} moments</div>
                </div>
                <div className="mt-3 space-y-2">
                  {group.moments.slice(0, 3).map((moment) => (
                    <div key={moment.id} className="rounded-lg border border-border bg-surface p-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-subtle">
                        <span>{formatTimestamp(moment.start_ms)}</span>
                      </div>
                      <HighlightedSnippet
                        as="div"
                        className="prose prose-sm mt-2 max-w-none dark:prose-invert"
                        snippet={moment.snippet}
                        highlights={moment.highlights}
                      />
                      <div className="mt-3 flex flex-wrap gap-3 text-sm">
                        <Link
                          className="action-link"
                          to={mentionLink(group.video.id, moment as SearchHit)}
                        >
                          Open cited moment
                        </Link>
                        <button
                          type="button"
                          className="nav-link"
                          onClick={() => {
                            void copyText(
                              quoteText(
                                group.video.id,
                                moment as SearchHit,
                                group.video.title || 'Untitled VOD'
                              )
                            )
                              .then(() => setFeedback('Quote copied.'))
                              .catch(() => setError('The quote could not be copied.'));
                          }}
                        >
                          Copy quote
                        </button>
                        <button
                          type="button"
                          className="nav-link"
                          disabled={savedKeys.has(
                            `${group.video.id}:${moment.start_ms}:${moment.end_ms}`
                          )}
                          onClick={() => saveMoment(group.video.id, moment as SearchHit)}
                        >
                          {savedKeys.has(`${group.video.id}:${moment.start_ms}:${moment.end_ms}`)
                            ? 'Saved moment'
                            : 'Save moment'}
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
        {(grouped?.groups?.length ?? 0) > evidenceLimit && (
          <button
            type="button"
            className="btn-secondary w-full"
            onClick={() => setEvidenceLimit((value) => value + 3)}
          >
            Show more evidence
          </button>
        )}
      </section>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-4 text-sm text-muted">
      No {label.toLowerCase()} yet.
    </div>
  );
}
