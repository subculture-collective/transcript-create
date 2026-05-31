import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  api,
  apiAddFavorite,
  apiListFavorites,
  favorites,
  useAuth,
  track,
} from '../services';
import type { Segment, TranscriptResponse, VideoInfo, SearchHit } from '../types/api';
// favorites, useAuth imported from services barrel
import { YouTubePlayer, UpgradeModal, ExportMenu } from '../components';
import type { YouTubePlayerHandle } from '../components/YouTubePlayer';
// track imported from services barrel
import { buildTimestampLink, formatDate, formatDuration, formatTimestamp, sourceLabel } from '../features/archive/format';

function secondsToYouTubeTs(s: number) {
  // Converts seconds to YouTube timestamp format
  return Math.max(0, Math.floor(s));
}

function msToHms(ms: number) {
  const total = Math.floor(ms / 1000);
  const hh = Math.floor(total / 3600)
    .toString()
    .padStart(2, '0');
  const mm = Math.floor((total % 3600) / 60)
    .toString()
    .padStart(2, '0');
  const ss = (total % 60).toString().padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

type TranscriptTurn = {
  key: string;
  speaker: string | null;
  segments: Array<{ segment: Segment; id: number; match?: SearchHit }>;
};

function speakerName(seg: Segment) {
  return seg.speaker_label?.trim() || null;
}

function normalizeTranscriptText(text: string) {
  return text
    .replace(/\s+/g, ' ')
    .replace(/\s+([,.!?;:])/g, '$1')
    .trim();
}

function copyText(text: string) {
  void navigator.clipboard?.writeText(text);
}

function shouldStartNewUnlabeledParagraph(
  previous: { segment: Segment; id: number; match?: SearchHit } | undefined,
  current: Segment,
  currentText: string
) {
  if (!previous) return true;

  const previousText = normalizeTranscriptText(previous.segment.text);
  const silenceGapMs = current.start_ms - previous.segment.end_ms;
  const previousEndsSentence = /[.!?]["')\]]?$/.test(previousText);
  const currentLooksLikeNewThought = /^[A-Z0-9"'“‘]/.test(currentText);
  const previousWordCount = previousText.split(/\s+/).filter(Boolean).length;

  return (
    silenceGapMs >= 1200 ||
    (previousEndsSentence && currentLooksLikeNewThought && previousWordCount >= 8)
  );
}

function buildTranscriptTurns(segments: Segment[], hits: SearchHit[] | null): TranscriptTurn[] {
  return segments.reduce<TranscriptTurn[]>((turns, segment, idx) => {
    const id = idx + 1;
    const speaker = speakerName(segment);
    const match = hits?.find((h) => h.start_ms >= segment.start_ms && h.start_ms < segment.end_ms);
    const last = turns.at(-1);
    const currentText = normalizeTranscriptText(segment.text);

    if (!currentText) return turns;

    if (!speaker) {
      const previous = last?.segments.at(-1);
      if (last && last.speaker === null && !shouldStartNewUnlabeledParagraph(previous, segment, currentText)) {
        last.segments.push({ segment, id, match });
        return turns;
      }

      turns.push({
        key: `paragraph-${id}`,
        speaker: null,
        segments: [{ segment, id, match }],
      });
      return turns;
    }

    if (last?.speaker === speaker) {
      last.segments.push({ segment, id, match });
      return turns;
    }

    turns.push({
      key: `${speaker}-${id}`,
      speaker,
      segments: [{ segment, id, match }],
    });
    return turns;
  }, []);
}

export default function VideoPage() {
  const { videoId } = useParams();
  const [params, setParams] = useSearchParams();
  const [video, setVideo] = useState<VideoInfo | null>(null);
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const { user } = useAuth();
  const [serverFavs, setServerFavs] = useState<
    Array<{ id: string; start_ms: number; end_ms: number }>
  >([]);
  const [activeSegId, setActiveSegId] = useState<number | null>(null);
  const [activeBlockIndex, setActiveBlockIndex] = useState<number | null>(null);
  const [isPlayingMatches, setIsPlayingMatches] = useState(false);
  const playerRef = useRef<YouTubePlayerHandle | null>(null);
  const [showUpgrade, setShowUpgrade] = useState(false);

  const startSeconds = useMemo(() => {
    const tStr = params.get('t');
    const t = tStr ? parseInt(tStr, 10) : 0;
    return Number.isFinite(t) ? t : 0;
  }, [params]);
  const transcriptQuery = useMemo(() => params.get('q') ?? '', [params]);

  useEffect(() => {
    if (!videoId) return;
    api
      .getVideo(videoId)
      .then(setVideo)
      .catch(() => setVideo(null));
    api
      .getTranscript(videoId)
      .then(setTranscript)
      .catch(() => setTranscript(null));
    if (transcriptQuery) {
      api
        .search(transcriptQuery, { video_id: videoId })
        .then((r) => setHits(r.hits))
        .catch(() => setHits(null));
    } else {
      setHits(null);
    }
    if (user) {
      apiListFavorites(videoId)
        .then((r) => {
          const filtered = r.items.map((i) => ({
            id: i.id,
            start_ms: i.start_ms,
            end_ms: i.end_ms,
          }));
          setServerFavs(filtered);
        })
        .catch(() => setServerFavs([]));
    } else {
      setServerFavs([]);
    }
  }, [videoId, transcriptQuery, user]);

  // Scroll to a hash if provided
  useEffect(() => {
    if (transcript && startSeconds > 0) {
      const startMs = startSeconds * 1000;
      const segIndex = transcript.segments.findIndex((seg) => startMs >= seg.start_ms && startMs < seg.end_ms);
      if (segIndex >= 0) {
        const block = transcript.blocks?.find((candidate) => candidate.segment_ids.includes(segIndex));
        const el = block ? document.getElementById(`block-${block.block_index}`) : document.getElementById(`seg-${segIndex + 1}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          setActiveSegId(segIndex + 1);
          setActiveBlockIndex(block?.block_index ?? null);
          return;
        }
      }
    }

    const hash = window.location.hash;
    if (hash) {
      const el = document.querySelector(hash);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
    }
  }, [startSeconds, transcript]);

  const jumpTo = useCallback((ms: number) => {
    const s = Math.floor(ms / 1000);
    setParams((prev: URLSearchParams) => {
      const p = new URLSearchParams(prev as unknown as string);
      p.set('t', String(s));
      return p;
    });
    playerRef.current?.seekTo(s, { play: true });
    track({ type: 'seek', payload: { videoId, seconds: s } });
  }, [setParams, videoId]);

  function onClickSegment(seg: Segment, id: number) {
    setActiveSegId(id);
    setActiveBlockIndex(null);
    jumpTo(seg.start_ms);
    // update hash for deep-linking this segment
    history.replaceState(null, '', `#seg-${id}`);
  }

  function onClickBlock(block: NonNullable<TranscriptResponse['blocks']>[number]) {
    const firstSegId = (block.segment_ids[0] ?? 0) + 1;
    setActiveBlockIndex(block.block_index);
    setActiveSegId(firstSegId);
    jumpTo(block.start_ms);
    history.replaceState(null, '', `#block-${block.block_index}`);
  }

  const start = useMemo(() => secondsToYouTubeTs(startSeconds), [startSeconds]);
  const matchIndices = useMemo(() => {
    if (!transcript || !hits) return [] as number[];
    const ids: number[] = [];
    transcript.segments.forEach((seg, idx) => {
      if (hits.find((h) => h.start_ms >= seg.start_ms && h.start_ms < seg.end_ms))
        ids.push(idx + 1);
    });
    return ids;
  }, [transcript, hits]);
  const matchIndicesKey = useMemo(() => matchIndices.join(','), [matchIndices]);
  const [matchCursor, setMatchCursor] = useState(0);
  useEffect(() => {
    setMatchCursor(0);
  }, [matchIndicesKey]);

  useEffect(() => {
    if (params.get('play') !== 'matches' || matchIndices.length === 0 || !transcript) return;
    const startMs = startSeconds * 1000;
    const startIndex = matchIndices.findIndex((segId) => transcript.segments[segId - 1]?.start_ms >= startMs);
    setMatchCursor(startIndex >= 0 ? startIndex : 0);
    setIsPlayingMatches(true);
    const segId = matchIndices[startIndex >= 0 ? startIndex : 0];
    const seg = transcript.segments[segId - 1];
    if (seg) {
      window.setTimeout(() => playerRef.current?.seekTo(Math.floor(seg.start_ms / 1000), { play: true }), 0);
    }
  }, [matchIndicesKey, matchIndices, params, startSeconds, transcript]);
  const formattedBlocks = useMemo(
    () => transcript?.blocks?.filter((block) => block.text.trim()) ?? [],
    [transcript?.blocks]
  );
  const hasFormattedBlocks = formattedBlocks.length > 0;

  function gotoMatch(direction: 1 | -1) {
    if (matchIndices.length === 0) return;
    const next = (matchCursor + direction + matchIndices.length) % matchIndices.length;
    setMatchCursor(next);
    const segId = matchIndices[next];
    const blockId = hasFormattedBlocks ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(segId - 1))?.block_index : null;
    const el = blockId !== null ? document.getElementById(`block-${blockId}`) : document.getElementById(`seg-${segId}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setActiveSegId(segId);
    setActiveBlockIndex(blockId ?? null);
    const seg = transcript?.segments[segId - 1];
    if (seg) jumpTo(seg.start_ms);
  }

  useEffect(() => {
    if (!isPlayingMatches || matchIndices.length === 0 || !transcript) return;
    const segId = matchIndices[matchCursor];
    const seg = transcript.segments[segId - 1];
    if (!seg) return;
    const delay = Math.min(Math.max(seg.end_ms - seg.start_ms + 600, 2500), 12000);
    const timeout = window.setTimeout(() => {
      if (matchCursor >= matchIndices.length - 1) {
        setIsPlayingMatches(false);
        return;
      }
      const next = matchCursor + 1;
      setMatchCursor(next);
      const nextSegId = matchIndices[next];
      const blockId = hasFormattedBlocks ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(nextSegId - 1))?.block_index : null;
      const el = blockId !== null ? document.getElementById(`block-${blockId}`) : document.getElementById(`seg-${nextSegId}`);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setActiveSegId(nextSegId);
      setActiveBlockIndex(blockId ?? null);
      const nextSeg = transcript.segments[nextSegId - 1];
      if (nextSeg) jumpTo(nextSeg.start_ms);
    }, delay);
    return () => window.clearTimeout(timeout);
  }, [formattedBlocks, hasFormattedBlocks, isPlayingMatches, jumpTo, matchCursor, matchIndices, transcript]);

  async function saveTranscriptMoment(segment: Segment, segIndex: number, text: string) {
    if (!videoId) return;
    try {
      if (user) {
        const created = await apiAddFavorite({ video_id: videoId, start_ms: segment.start_ms, end_ms: segment.end_ms, text });
        setServerFavs((current) => [{ id: created.id, start_ms: segment.start_ms, end_ms: segment.end_ms }, ...current]);
      } else {
        favorites.toggle({ videoId, segIndex, startMs: segment.start_ms, endMs: segment.end_ms, text });
      }
      track({ type: 'favorite_add', payload: { videoId, start_ms: segment.start_ms } });
    } catch (err) {
      console.error('Failed to save transcript moment', err);
    }
  }

  function copyTranscriptQuote(segment: Segment, text: string, segIndex: number) {
    if (!videoId) return;
    const url = `${window.location.origin}${buildTimestampLink(videoId, segment.start_ms, segIndex)}`;
    copyText(`“${normalizeTranscriptText(text)}”\n\n— ${episodeTitle}, ${formatTimestamp(segment.start_ms)}\n${url}`);
  }

  const transcriptTurns = useMemo(
    () => buildTranscriptTurns(transcript?.segments ?? [], hits),
    [transcript?.segments, hits]
  );
  const episodeTitle = video?.title ?? 'Loading episode...';
  return (
    <div className="space-y-6">
      <header className="surface-card space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="mb-1 text-sm font-medium uppercase tracking-wide text-subtle">Episode transcript</p>
            <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
              {episodeTitle}
            </h1>
            {transcript?.source_label && (
              <p className="mt-2 text-sm text-muted">
                Showing {transcript.source_label}
                {transcript.source === 'youtube' ? ' because Whisper is not available yet.' : ''}
              </p>
            )}
          </div>
          {video && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <ExportMenu
                videoId={video.id}
                isPro={user?.plan === 'pro'}
                onRequireUpgrade={() => setShowUpgrade(true)}
              />
            </div>
          )}
        </div>
        <UpgradeModal open={showUpgrade} onClose={() => setShowUpgrade(false)} />
        <form
          className="grid gap-3 sm:grid-cols-[1fr_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const data = new FormData(form);
            const val = String(data.get('transcript-search') ?? '').trim();
            const next = new URLSearchParams(params);
            if (val) next.set('q', val);
            else next.delete('q');
            setParams(next);
          }}
        >
          <label htmlFor="transcript-search" className="sr-only">
            Search inside this episode
          </label>
          <input
            id="transcript-search"
            name="transcript-search"
            type="search"
            defaultValue={params.get('q') ?? ''}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const val = (e.target as HTMLInputElement).value;
                const next = new URLSearchParams(params);
                if (val) next.set('q', val);
                else next.delete('q');
                setParams(next);
              }
            }}
            placeholder="Search inside this episode..."
            className="form-control"
            aria-label="Search inside this episode"
          />
          <button className="btn-primary" type="submit">
            Search episode
          </button>
        </form>

        {video && (
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(16rem,0.8fr)]">
            <div className="rounded-2xl border border-border bg-surface-muted p-4">
              <div className="text-xs uppercase tracking-[0.24em] text-subtle">Episode details</div>
              <dl className="mt-3 grid gap-3 sm:grid-cols-3">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-subtle">Channel</dt>
                  <dd className="mt-1 font-medium text-ink">{video.channel_name || 'Unknown channel'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-subtle">Upload date</dt>
                  <dd className="mt-1 font-medium text-ink">{formatDate(video.uploaded_at ?? null)}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-subtle">Duration</dt>
                  <dd className="mt-1 font-medium text-ink">{formatDuration(video.duration_seconds)}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-subtle">Transcript source</dt>
                  <dd className="mt-1 font-medium text-ink">{sourceLabel(transcript?.source ?? 'best')}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-subtle">Video ID</dt>
                  <dd className="mt-1 font-mono text-sm text-ink">{video.id}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-subtle">YouTube ID</dt>
                  <dd className="mt-1 font-mono text-sm text-ink">{video.youtube_id}</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-2xl border border-dashed border-border bg-surface p-4">
              <div className="text-xs uppercase tracking-[0.24em] text-subtle">Future work</div>
              <div className="mt-2 font-medium text-ink">Topic extraction coming later</div>
              <p className="mt-2 text-sm text-muted">
                This space stays intentionally disabled until citation-backed topic extraction exists.
              </p>
            </div>
          </div>
        )}
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:items-start">
        <aside className="lg:sticky lg:top-6 lg:col-span-1">
          {video ? (
            <YouTubePlayer
              ref={playerRef}
              videoId={video.youtube_id}
              start={start}
              title={video?.title ?? undefined}
            />
          ) : (
            <div className="aspect-video w-full overflow-hidden rounded-lg border border-border bg-black">
              <div className="flex h-full items-center justify-center text-subtle" role="status" aria-live="polite">
                <span className="inline-block animate-spin text-3xl mr-3" aria-hidden="true">⟳</span>
                Loading player…
              </div>
            </div>
          )}
        </aside>

        <section className="lg:col-span-2">
          <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="section-title">Episode transcript</h2>
          {matchIndices.length > 0 && (
            <div className="flex items-center gap-2 text-sm text-muted" role="group" aria-label="Search navigation">
              <button
                className="btn-secondary"
                onClick={() => gotoMatch(-1)}
                aria-label="Go to previous match"
              >
                Prev
              </button>
              <span aria-live="polite" aria-atomic="true">
                {matchCursor + 1} / {matchIndices.length}
              </span>
              <button
                className="btn-secondary"
                onClick={() => gotoMatch(1)}
                aria-label="Go to next match"
              >
                Next
              </button>
              <button
                className="btn-secondary"
                onClick={() => setIsPlayingMatches((value) => !value)}
                aria-label="Play all matching transcript moments"
              >
                {isPlayingMatches ? 'Stop play all' : 'Play all matches'}
              </button>
            </div>
          )}
          </div>
        {!transcript && (
          <div className="py-8 text-center text-muted" role="status" aria-live="polite">
            <span className="inline-block animate-spin text-2xl mb-2" aria-hidden="true">⟳</span>
            <p>Loading transcript…</p>
          </div>
        )}
        {transcript &&
          (hasFormattedBlocks ? (
            <article className="surface-card space-y-7" role="list" aria-label="Formatted transcript document">
              {formattedBlocks.map((block) => {
                const isFavorite = block.segment_ids.some((segIdx) => favorites.has({ videoId: videoId!, segIndex: segIdx + 1 }));
                const isServerFavorite = serverFavs.some((favorite) => favorite.start_ms === block.start_ms && favorite.end_ms === block.end_ms);
                const isHighlighted = block.segment_ids.some((segIdx) =>
                  hits?.some((h) => h.start_ms >= transcript.segments[segIdx]?.start_ms && h.start_ms < transcript.segments[segIdx]?.end_ms)
                );
                const isActive = activeBlockIndex === block.block_index || block.segment_ids.some((segIdx) => activeSegId === segIdx + 1);
                return (
                  <section
                    key={block.block_index}
                    id={`block-${block.block_index}`}
                    className={`rounded-xl px-1 py-1 transition-colors ${isActive ? 'bg-accent-soft/60 ring-1 ring-accent' : ''}`}
                    role="listitem"
                  >
                    {block.speaker_label && (
                      <div className="mb-2 text-sm font-semibold uppercase tracking-wide text-subtle">
                        {block.speaker_label}
                      </div>
                    )}
                    <div className="space-y-3 text-lg leading-8 text-ink">
                      <button
                        type="button"
                        onClick={() => onClickBlock(block)}
                        className={`w-full cursor-pointer rounded-lg px-3 py-2 text-left font-serif text-[1.05rem] leading-8 transition-colors hover:bg-surface-muted focus:bg-surface-muted ${
                          isHighlighted && !isActive ? 'bg-warning-soft ring-1 ring-warning' : ''
                        } ${isFavorite || isServerFavorite ? 'decoration-warning underline decoration-2 underline-offset-4' : ''}`}
                        aria-label={`Play ${block.speaker_label ?? 'paragraph'} from ${msToHms(block.start_ms)}`}
                      >
                        {block.text}
                      </button>
                      {isActive && (
                        <div className="flex flex-wrap items-center gap-3 border-l-2 border-accent pl-3 text-sm">
                          <span className="text-xs uppercase tracking-wide text-subtle">Selected {formatTimestamp(block.start_ms)}</span>
                          <button type="button" className="nav-link" disabled={isFavorite || isServerFavorite} onClick={() => saveTranscriptMoment({ start_ms: block.start_ms, end_ms: block.end_ms, text: block.text, speaker_label: block.speaker_label }, (block.segment_ids[0] ?? 0) + 1, block.text)}>
                            {isFavorite || isServerFavorite ? 'Saved moment' : 'Save moment'}
                          </button>
                          <button type="button" className="nav-link" onClick={() => copyTranscriptQuote({ start_ms: block.start_ms, end_ms: block.end_ms, text: block.text, speaker_label: block.speaker_label }, block.text, (block.segment_ids[0] ?? 0) + 1)}>
                            Copy quote
                          </button>
                        </div>
                      )}
                    </div>
                  </section>
                );
              })}
            </article>
          ) : (
            <div className="surface-card space-y-6" role="list" aria-label="Transcript paragraphs">
              {transcriptTurns.map((turn) => {
                const activeEntry = turn.segments.find(({ id }) => id === activeSegId);
                return (
                  <section
                    key={turn.key}
                    className={turn.speaker ? 'grid gap-3 sm:grid-cols-[8rem_1fr]' : 'block'}
                    role="listitem"
                  >
                    {turn.speaker && <div className="font-semibold text-ink">{turn.speaker}:</div>}
                    <div className="space-y-2 text-lg leading-8 text-ink">
                      <p className="whitespace-normal font-serif text-[1.05rem]">
                        {turn.segments.map(({ segment: seg, id, match }) => {
                        const isServerFav = !!serverFavs.find(
                          (f) => f.start_ms === seg.start_ms && f.end_ms === seg.end_ms
                        );
                        const isFavorite = isServerFav || favorites.has({ videoId: videoId!, segIndex: id });
                        return (
                          <button
                            id={`seg-${id}`}
                            key={id}
                            type="button"
                            onClick={() => onClickSegment(seg, id)}
                            className={`mx-0.5 cursor-pointer rounded px-1 text-left leading-8 transition-colors hover:bg-surface-muted focus:bg-surface-muted ${
                              activeSegId === id || match ? 'bg-accent-soft ring-1 ring-accent' : ''
                            } ${isFavorite ? 'ring-1 ring-warning' : ''}`}
                            aria-label={`Play ${turn.speaker ?? 'paragraph'} from ${msToHms(seg.start_ms)}`}
                          >
                            {normalizeTranscriptText(seg.text)}{' '}
                          </button>
                        );
                      })}
                    </p>
                    {turn.segments.some(({ match }) => match) && (
                      <div className="rounded bg-warning-soft p-2 text-xs text-ink" role="note">
                        <div className="mb-1 font-medium">Search match in this turn</div>
                        {turn.segments
                          .filter(({ match }) => match)
                          .map(({ match, id }) => (
                            <div key={id} className="prose prose-xs max-w-none" dangerouslySetInnerHTML={{ __html: match?.snippet ?? '' }} />
                          ))}
                      </div>
                    )}
                    {activeEntry && (
                      <div className="flex flex-wrap items-center gap-3 border-l-2 border-accent pl-3 text-sm">
                        <span className="text-xs uppercase tracking-wide text-subtle">Selected {formatTimestamp(activeEntry.segment.start_ms)}</span>
                        <button type="button" className="nav-link" onClick={() => saveTranscriptMoment(activeEntry.segment, activeEntry.id, normalizeTranscriptText(activeEntry.segment.text))}>
                          Save moment
                        </button>
                        <button type="button" className="nav-link" onClick={() => copyTranscriptQuote(activeEntry.segment, activeEntry.segment.text, activeEntry.id)}>
                          Copy quote
                        </button>
                      </div>
                    )}
                  </div>
                </section>
                );
              })}
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
