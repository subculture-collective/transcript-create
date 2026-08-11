import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { HTTPError } from 'ky';
import {
  api,
  apiAddFavorite,
  apiDeleteFavorite,
  apiListFavorites,
  favorites,
  useAuth,
  track,
} from '../services';
import type { Segment, TranscriptResponse, VideoInfo, SearchHit, VideoChapter } from '../types/api';
// favorites, useAuth imported from services barrel
import { ExportMenu } from '../components';
import type { YouTubePlayerHandle } from '../components/YouTubePlayer';
// track imported from services barrel
import { buildTimestampLink, formatTimestamp, formatVideoTitle } from '../features/archive/format';
import type { TranscriptSource } from '../features/archive/format';
import {
  buildTranscriptTurns,
  normalizeTranscriptText,
} from '../features/videoTranscript/transcript';
import {
  FormattedTranscriptDocument,
  EpisodeIntelligence,
  PlaybackProgress,
  PlayerPanel,
  PlainTranscriptTurns,
  TranscriptQualityNotice,
  TranscriptSearchBar,
  VideoDetailsPanel,
  VideoHeader,
} from '../components/video';

function secondsToYouTubeTs(s: number) {
  return Math.max(0, Math.floor(s));
}

async function copyText(text: string) {
  if (!navigator.clipboard) throw new Error('Clipboard unavailable');
  await navigator.clipboard.writeText(text);
}

export default function VideoPage() {
  const { videoId } = useParams();
  const [params, setParams] = useSearchParams();
  const [video, setVideo] = useState<VideoInfo | null>(null);
  const [videoStatus, setVideoStatus] = useState<'loading' | 'ready' | 'missing' | 'error'>(
    'loading'
  );
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [transcriptStatus, setTranscriptStatus] = useState<'loading' | 'ready' | 'error'>(
    'loading'
  );
  const [chapters, setChapters] = useState<VideoChapter[]>([]);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const { user } = useAuth();
  const [serverFavs, setServerFavs] = useState<
    Array<{ id: string; start_ms: number; end_ms: number }>
  >([]);
  const [activeSegId, setActiveSegId] = useState<number | null>(null);
  const [activeSentenceId, setActiveSentenceId] = useState<string | null>(null);
  const [activeBlockIndex, setActiveBlockIndex] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<'standard' | 'theater' | 'reader'>('standard');
  const [isPlayingMatches, setIsPlayingMatches] = useState(false);
  const [autoFollowEnabled, setAutoFollowEnabled] = useState(true);
  const [operationFeedback, setOperationFeedback] = useState<string | null>(null);
  const playerRef = useRef<YouTubePlayerHandle | null>(null);
  const autoFollowScrollTimeoutRef = useRef<number | null>(null);

  const startSeconds = useMemo(() => {
    const tStr = params.get('t');
    const t = tStr ? parseInt(tStr, 10) : 0;
    return Number.isFinite(t) ? t : 0;
  }, [params]);
  const transcriptQuery = useMemo(() => params.get('q') ?? '', [params]);

  const scrollElementIntoView = useCallback(
    (element: Element | null, options?: ScrollIntoViewOptions) => {
      if (!element) return;
      if (autoFollowScrollTimeoutRef.current != null) {
        window.clearTimeout(autoFollowScrollTimeoutRef.current);
      }
      autoFollowScrollTimeoutRef.current = window.setTimeout(() => {
        autoFollowScrollTimeoutRef.current = null;
      }, 1000);
      element.scrollIntoView(options ?? { behavior: 'smooth', block: 'center' });
    },
    []
  );

  const resumeAutoFollow = useCallback(() => {
    setAutoFollowEnabled(true);
    scrollElementIntoView(document.querySelector('[data-current-sentence="true"]'), {
      behavior: 'smooth',
      block: 'center',
      inline: 'nearest',
    });
  }, [scrollElementIntoView]);
  const autoScrollToPlayback = useCallback(
    (element: HTMLElement) =>
      scrollElementIntoView(element, {
        behavior: 'smooth',
        block: 'center',
        inline: 'nearest',
      }),
    [scrollElementIntoView]
  );

  const loadTranscript = useCallback(
    async (id: string, source: 'best' | 'whisper' | 'youtube' = 'best') => {
      setTranscript(null);
      setTranscriptStatus('loading');
      try {
        const response = await api.getTranscript(id, source);
        setTranscript(response);
        setTranscriptStatus('ready');
      } catch {
        setTranscript(null);
        setTranscriptStatus('error');
      }
    },
    []
  );

  useEffect(() => {
    if (!videoId) return;
    setVideo(null);
    setVideoStatus('loading');
    setChapters([]);
    api
      .getVideo(videoId)
      .then((response) => {
        setVideo(response);
        setVideoStatus('ready');
        void loadTranscript(videoId, response.has_whisper_transcript ? 'whisper' : 'best');
      })
      .catch((error: unknown) => {
        setVideo(null);
        const status =
          error instanceof HTTPError
            ? error.response.status
            : (error as { response?: { status?: number } })?.response?.status;
        setVideoStatus(status === 404 ? 'missing' : 'error');
        setTranscriptStatus('error');
      });
    api
      .getVideoChapters(videoId)
      .then((response) => setChapters(response.chapters ?? []))
      .catch(() => setChapters([]));
  }, [loadTranscript, videoId]);

  useEffect(() => {
    if (!video) return;
    document.title = `${formatVideoTitle(video.title, video.uploaded_at)} | HasanAra`;
  }, [video]);

  useEffect(() => {
    if (!videoId) return;
    if (transcriptQuery) {
      api
        .search(transcriptQuery, { video_id: videoId })
        .then((r) => setHits(r.hits))
        .catch(() => setHits(null));
    } else {
      setHits(null);
    }
  }, [transcriptQuery, videoId]);

  useEffect(() => {
    if (!videoId) return;
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
  }, [user, videoId]);

  useEffect(() => {
    const unlockAutoFollow = () => setAutoFollowEnabled(false);
    const onScroll = () => {
      if (autoFollowScrollTimeoutRef.current != null) return;
      unlockAutoFollow();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End', ' '].includes(event.key)) {
        unlockAutoFollow();
      }
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('wheel', unlockAutoFollow, { passive: true });
    window.addEventListener('touchstart', unlockAutoFollow, { passive: true });
    window.addEventListener('keydown', onKeyDown);

    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('wheel', unlockAutoFollow);
      window.removeEventListener('touchstart', unlockAutoFollow);
      window.removeEventListener('keydown', onKeyDown);
      if (autoFollowScrollTimeoutRef.current != null) {
        window.clearTimeout(autoFollowScrollTimeoutRef.current);
      }
    };
  }, []);

  // Scroll/select by explicit hash first. The `t=` URL param is whole-second
  // precision, so using it first can select the previous paragraph for starts
  // like 12.8s. Hashes preserve the exact segment/block identity.
  useEffect(() => {
    const hash = window.location.hash;
    if (hash) {
      const segMatch = hash.match(/^#seg-(\d+)(?:-s-(.+))?$/);
      if (segMatch) {
        const segId = Number(segMatch[1]);
        const sentenceSuffix = segMatch[2];
        const seg = transcript?.segments[segId - 1];
        const block = transcript?.blocks?.find((candidate) =>
          candidate.segment_ids.includes(segId - 1)
        );
        const sentenceId = sentenceSuffix
          ? `${block?.block_index}-${segId - 1}-s-${sentenceSuffix}`
          : null;
        const el = sentenceSuffix
          ? document.getElementById(`seg-${segId}-s-${sentenceSuffix}`)
          : null;
        const target =
          el ??
          document.getElementById(`seg-${segId}`) ??
          (block ? document.getElementById(`block-${block.block_index}`) : null);
        if (seg && target) {
          scrollElementIntoView(target, { behavior: 'smooth', block: 'center' });
          setActiveSegId(segId);
          setActiveSentenceId(sentenceId);
          setActiveBlockIndex(block?.block_index ?? null);
          return;
        }
      }

      const blockMatch = hash.match(/^#block-(\d+)$/);
      if (blockMatch) {
        const blockIndex = Number(blockMatch[1]);
        const block = transcript?.blocks?.find((candidate) => candidate.block_index === blockIndex);
        const el = document.getElementById(`block-${blockIndex}`);
        if (block && el) {
          scrollElementIntoView(el, { behavior: 'smooth', block: 'center' });
          setActiveSegId((block.segment_ids[0] ?? 0) + 1);
          setActiveSentenceId(null);
          setActiveBlockIndex(block.block_index);
          return;
        }
      }

      const el = document.querySelector(hash);
      if (el) {
        scrollElementIntoView(el, { behavior: 'smooth', block: 'center' });
        return;
      }
    }

    if (transcript && startSeconds > 0) {
      const startMs = startSeconds * 1000;
      const segIndex = transcript.segments.findIndex(
        (seg) => startMs >= seg.start_ms && startMs < seg.end_ms
      );
      if (segIndex >= 0) {
        const block = transcript.blocks?.find((candidate) =>
          candidate.segment_ids.includes(segIndex)
        );
        const el = block
          ? document.getElementById(`block-${block.block_index}`)
          : document.getElementById(`seg-${segIndex + 1}`);
        if (el) {
          scrollElementIntoView(el, { behavior: 'smooth', block: 'center' });
          setActiveSegId(segIndex + 1);
          setActiveSentenceId(null);
          setActiveBlockIndex(block?.block_index ?? null);
          return;
        }
      }
    }
  }, [scrollElementIntoView, startSeconds, transcript]);

  const jumpTo = useCallback(
    (ms: number) => {
      const s = Math.floor(ms / 1000);
      setParams((prev: URLSearchParams) => {
        const p = new URLSearchParams(prev as unknown as string);
        p.set('t', String(s));
        return p;
      });
      playerRef.current?.seekTo(s, { play: true });
      track({ type: 'seek', payload: { videoId, seconds: s } });
    },
    [setParams, videoId]
  );

  function onClickSegment(seg: Segment, id: number) {
    setActiveSegId(id);
    setActiveSentenceId(null);
    setActiveBlockIndex(null);
    jumpTo(seg.start_ms);
    // update hash for deep-linking this segment
    history.replaceState(null, '', `#seg-${id}`);
  }

  function onClickFormattedSentence(segment: Segment, segIndex: number, sentenceId: string) {
    setActiveSegId(segIndex);
    setActiveSentenceId(sentenceId);
    const blockId = hasFormattedBlocks
      ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(segIndex - 1))
          ?.block_index
      : null;
    setActiveBlockIndex(blockId ?? null);
    jumpTo(segment.start_ms);
    const sentenceSuffix = sentenceId.split('-s-').at(1);
    history.replaceState(
      null,
      '',
      sentenceSuffix ? `#seg-${segIndex}-s-${sentenceSuffix}` : `#seg-${segIndex}`
    );
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
  useEffect(() => {
    setMatchCursor(0);
  }, [matchIndices]);

  useEffect(() => {
    if (params.get('play') !== 'matches' || matchIndices.length === 0 || !transcript) return;
    const startMs = startSeconds * 1000;
    const startIndex = matchIndices.findIndex(
      (segId) => transcript.segments[segId - 1]?.start_ms >= startMs
    );
    setMatchCursor(startIndex >= 0 ? startIndex : 0);
    setIsPlayingMatches(true);
    const segId = matchIndices[startIndex >= 0 ? startIndex : 0];
    const seg = transcript.segments[segId - 1];
    if (seg) {
      window.setTimeout(
        () => playerRef.current?.seekTo(Math.floor(seg.start_ms / 1000), { play: true }),
        0
      );
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
    const blockId = hasFormattedBlocks
      ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(segId - 1))?.block_index
      : null;
    const el =
      blockId !== null
        ? document.getElementById(`block-${blockId}`)
        : document.getElementById(`seg-${segId}`);
    if (el) scrollElementIntoView(el, { behavior: 'smooth', block: 'center' });
    setActiveSegId(segId);
    setActiveSentenceId(null);
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
      const blockId = hasFormattedBlocks
        ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(nextSegId - 1))
            ?.block_index
        : null;
      const el =
        blockId !== null
          ? document.getElementById(`block-${blockId}`)
          : document.getElementById(`seg-${nextSegId}`);
      if (el) scrollElementIntoView(el, { behavior: 'smooth', block: 'center' });
      setActiveSegId(nextSegId);
      setActiveSentenceId(null);
      setActiveBlockIndex(blockId ?? null);
      const nextSeg = transcript.segments[nextSegId - 1];
      if (nextSeg) jumpTo(nextSeg.start_ms);
    }, delay);
    return () => window.clearTimeout(timeout);
  }, [
    formattedBlocks,
    hasFormattedBlocks,
    isPlayingMatches,
    jumpTo,
    matchCursor,
    matchIndices,
    scrollElementIntoView,
    transcript,
  ]);

  async function saveTranscriptMoment(segment: Segment, segIndex: number, text: string) {
    if (!videoId) return;
    try {
      if (user) {
        const existing = serverFavs.find(
          (favorite) => favorite.start_ms === segment.start_ms && favorite.end_ms === segment.end_ms
        );
        if (existing) {
          await apiDeleteFavorite(existing.id);
          setServerFavs((current) => current.filter((favorite) => favorite.id !== existing.id));
          track({ type: 'favorite_remove', payload: { videoId, start_ms: segment.start_ms } });
          setOperationFeedback('Transcript moment removed.');
          return;
        }
        const created = await apiAddFavorite({
          video_id: videoId,
          start_ms: segment.start_ms,
          end_ms: segment.end_ms,
          text,
        });
        setServerFavs((current) => [
          { id: created.id, start_ms: segment.start_ms, end_ms: segment.end_ms },
          ...current,
        ]);
      } else {
        const wasSaved = favorites.has({ videoId, segIndex });
        favorites.toggle({
          videoId,
          segIndex,
          startMs: segment.start_ms,
          endMs: segment.end_ms,
          text,
        });
        track({
          type: wasSaved ? 'favorite_remove' : 'favorite_add',
          payload: { videoId, start_ms: segment.start_ms },
        });
        setOperationFeedback(wasSaved ? 'Transcript moment removed.' : 'Transcript moment saved.');
        return;
      }
      track({ type: 'favorite_add', payload: { videoId, start_ms: segment.start_ms } });
      setOperationFeedback('Transcript moment saved.');
    } catch (err) {
      console.error('Failed to save transcript moment', err);
      setOperationFeedback('The transcript moment could not be saved.');
    }
  }

  async function copyTranscriptQuote(segment: Segment, text: string, segIndex: number) {
    if (!videoId) return;
    const url = `${window.location.origin}${buildTimestampLink(videoId, segment.start_ms, segIndex)}`;
    try {
      await copyText(
        `“${normalizeTranscriptText(text)}”\n\n— ${episodeTitle}, ${formatTimestamp(segment.start_ms)}\n${url}`
      );
      setOperationFeedback('Quote copied.');
    } catch {
      setOperationFeedback('The quote could not be copied.');
    }
  }

  const transcriptTurns = useMemo(
    () => buildTranscriptTurns(transcript?.segments ?? [], hits),
    [transcript?.segments, hits]
  );
  const isSavedSegment = useCallback(
    (segment: Segment, segIndex: number) => {
      if (!videoId) return false;
      return (
        serverFavs.some(
          (favorite) => favorite.start_ms === segment.start_ms && favorite.end_ms === segment.end_ms
        ) || favorites.has({ videoId, segIndex })
      );
    },
    [serverFavs, videoId]
  );
  const episodeTitle = video ? formatVideoTitle(video.title, video.uploaded_at) : 'Loading VOD...';

  useEffect(() => {
    if (!video) return;
    document.title = `${episodeTitle} | HasanAra`;
  }, [episodeTitle, video]);

  function selectChapter(chapter: VideoChapter) {
    jumpTo(chapter.start_ms);
    const evidence = chapter.evidence[0];
    const target = evidence ? document.getElementById(`block-${evidence.block_index}`) : null;
    scrollElementIntoView(target, { behavior: 'smooth', block: 'start' });
  }
  if (videoStatus === 'missing') {
    return (
      <section className="mx-auto max-w-2xl p-8 text-center" role="alert">
        <div className="archive-eyebrow">Missing episode</div>
        <h1 className="mt-3 text-3xl font-semibold text-ink">This video is not in the archive</h1>
        <p className="mt-3 text-muted">It may have been removed or the link may be incorrect.</p>
        <Link className="btn mt-6 inline-flex" to="/episodes">
          Browse episodes
        </Link>
      </section>
    );
  }
  if (videoStatus === 'error' && !video) {
    return (
      <section className="mx-auto max-w-2xl p-8 text-center" role="alert">
        <h1 className="text-3xl font-semibold text-ink">Episode unavailable</h1>
        <p className="mt-3 text-muted">The archive could not load this episode right now.</p>
        <button className="btn mt-6" type="button" onClick={() => window.location.reload()}>
          Retry
        </button>
      </section>
    );
  }
  return (
    <div className="episode-page space-y-7">
      <VideoHeader title={episodeTitle} actions={video ? <ExportMenu videoId={video.id} /> : null}>
        {video && <VideoDetailsPanel video={video} />}
      </VideoHeader>
      {operationFeedback && (
        <div className="text-sm text-success" role="status">
          {operationFeedback}
        </div>
      )}
      {video && <EpisodeIntelligence videoId={video.id} />}

      <div className={viewMode === 'standard' ? 'transcript-layout' : 'space-y-6'}>
        <aside
          className={
            viewMode === 'standard'
              ? 'transcript-rail'
              : viewMode === 'theater'
                ? 'mx-auto max-w-6xl space-y-4'
                : 'hidden'
          }
        >
          {video && (
            <div>
              <PlayerPanel video={video} start={start} playerRef={playerRef} />
            </div>
          )}
          <div className="rail-panel">
            <div className="mb-3 flex items-center justify-between">
              <span className="meta-label">Reading mode</span>
              <span className="font-mono text-[10px] text-subtle">
                {transcript?.segments.length.toLocaleString() ?? '—'} segments
              </span>
            </div>
            <div className="view-switch" role="group" aria-label="Transcript layout">
              {(['standard', 'theater', 'reader'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={viewMode === mode ? 'view-switch-active' : ''}
                  aria-pressed={viewMode === mode}
                  onClick={() => setViewMode(mode)}
                >
                  {mode === 'standard' ? 'Split' : mode === 'theater' ? 'Watch' : 'Read'}
                </button>
              ))}
            </div>
            <p className="mt-3 text-xs leading-5 text-subtle">
              Select any sentence to play from that moment. Scroll manually to pause auto-follow.
            </p>
            <div className="mt-4 border-t border-border/70 pt-4">
              {autoFollowEnabled ? (
                <div
                  className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-accent"
                  role="status"
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full bg-accent shadow-[0_0_8px_rgba(183,255,60,0.65)]"
                    aria-hidden="true"
                  />
                  Following live transcript
                </div>
              ) : (
                <button type="button" className="follow-live-button" onClick={resumeAutoFollow}>
                  <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
                  Enable follow live
                </button>
              )}
            </div>
          </div>
          <PlaybackProgress
            chapters={chapters}
            onSelectChapter={selectChapter}
            playerRef={playerRef}
            transcriptKey={`${videoId}:${transcript?.segments.length ?? 0}:${formattedBlocks.length}`}
            autoFollow={autoFollowEnabled}
            onAutoScroll={autoScrollToPlayback}
          />
        </aside>

        <section
          className={viewMode === 'standard' ? 'min-w-0' : 'mx-auto max-w-5xl'}
          aria-labelledby="transcript-title"
        >
          <div className="transcript-shell">
            <header className="transcript-toolbar">
              <div className="flex flex-col gap-4 border-b border-border/70 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span
                      className="h-2 w-2 rounded-full bg-accent shadow-[0_0_12px_rgba(183,255,60,0.65)]"
                      aria-hidden="true"
                    />
                    <h2
                      id="transcript-title"
                      className="text-lg font-semibold tracking-[-0.025em] text-ink"
                    >
                      Interactive transcript
                    </h2>
                  </div>
                  <p className="text-xs text-subtle">
                    Timecoded, searchable, and linked to the source
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {viewMode !== 'standard' && (
                    <div className="view-switch" role="group" aria-label="Transcript layout">
                      {(['standard', 'theater', 'reader'] as const).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          className={viewMode === mode ? 'view-switch-active' : ''}
                          onClick={() => setViewMode(mode)}
                        >
                          {mode === 'standard' ? 'Split' : mode === 'theater' ? 'Watch' : 'Read'}
                        </button>
                      ))}
                    </div>
                  )}
                  {viewMode === 'reader' && video && (
                    <button
                      type="button"
                      className="toolbar-button"
                      onClick={() => playerRef.current?.togglePlay()}
                      aria-label="Toggle playback"
                    >
                      Play / pause
                    </button>
                  )}
                  {!autoFollowEnabled && (
                    <button
                      type="button"
                      className="toolbar-button toolbar-button-accent"
                      onClick={resumeAutoFollow}
                      aria-label="Follow current sentence"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-accent" /> Follow live
                    </button>
                  )}
                </div>
              </div>

              <div className="grid gap-3 px-4 py-4 sm:px-6 xl:grid-cols-[minmax(16rem,1fr)_auto] xl:items-center">
                <TranscriptSearchBar
                  initialQuery={params.get('q') ?? ''}
                  onSearch={(value) => {
                    const next = new URLSearchParams(params);
                    if (value) next.set('q', value);
                    else next.delete('q');
                    setParams(next);
                  }}
                />
                {matchIndices.length > 0 && (
                  <div
                    className="flex flex-wrap items-center gap-1.5"
                    role="group"
                    aria-label="Search navigation"
                  >
                    <span
                      className="mr-1 min-w-14 text-center font-mono text-xs text-muted"
                      aria-live="polite"
                      aria-atomic="true"
                    >
                      {matchCursor + 1} / {matchIndices.length}
                    </span>
                    <button
                      className="toolbar-button"
                      onClick={() => gotoMatch(-1)}
                      aria-label="Go to previous match"
                    >
                      ←
                    </button>
                    <button
                      className="toolbar-button"
                      onClick={() => gotoMatch(1)}
                      aria-label="Go to next match"
                    >
                      →
                    </button>
                    <button
                      className="toolbar-button"
                      onClick={() => setIsPlayingMatches((value) => !value)}
                      aria-label="Play all matching transcript moments"
                    >
                      {isPlayingMatches ? 'Stop' : 'Play matches'}
                    </button>
                  </div>
                )}
              </div>
            </header>

            <div className="transcript-body">
              {transcriptStatus === 'loading' && (
                <div className="py-24 text-center text-muted" role="status" aria-live="polite">
                  <span
                    className="mb-4 inline-block h-7 w-7 animate-spin rounded-full border-2 border-border border-t-accent"
                    aria-hidden="true"
                  />
                  <p className="font-mono text-xs uppercase tracking-[0.18em]">
                    Loading transcript
                  </p>
                </div>
              )}
              {transcriptStatus === 'error' && (
                <div className="mx-auto max-w-lg px-6 py-24 text-center" role="alert">
                  <div
                    className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full border border-danger/20 bg-danger-soft text-danger"
                    aria-hidden="true"
                  >
                    !
                  </div>
                  <h3 className="text-lg font-semibold text-ink">
                    Transcript took too long to load
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-muted">
                    The source transcript is still available. Try the request again without leaving
                    this episode.
                  </p>
                  <button
                    type="button"
                    className="btn-primary mt-5"
                    onClick={() =>
                      videoId &&
                      void loadTranscript(
                        videoId,
                        video?.has_whisper_transcript ? 'whisper' : 'best'
                      )
                    }
                  >
                    Try again
                  </button>
                </div>
              )}
              {transcriptStatus === 'ready' &&
                transcript &&
                (hasFormattedBlocks ? (
                  <>
                    <TranscriptQualityNotice
                      source={(transcript.source ?? 'whisper') as TranscriptSource}
                      sourceLabel={transcript.source_label}
                      blocks={formattedBlocks}
                    />
                    <FormattedTranscriptDocument
                      source={(transcript.source ?? 'whisper') as TranscriptSource}
                      blocks={formattedBlocks}
                      transcriptSegments={transcript.segments}
                      hits={hits}
                      activeBlockIndex={activeBlockIndex}
                      activeSegId={activeSegId}
                      activeSentenceId={activeSentenceId}
                      isSavedSegment={isSavedSegment}
                      onClickSentence={onClickFormattedSentence}
                      onSaveMoment={saveTranscriptMoment}
                      onCopyQuote={copyTranscriptQuote}
                    />
                  </>
                ) : (
                  <>
                    <TranscriptQualityNotice
                      source={(transcript.source ?? 'whisper') as TranscriptSource}
                      sourceLabel={transcript.source_label}
                      blocks={[]}
                    />
                    <PlainTranscriptTurns
                      turns={transcriptTurns}
                      source={(transcript.source ?? 'whisper') as TranscriptSource}
                      activeSegId={activeSegId}
                      isSavedSegment={isSavedSegment}
                      onClickSegment={onClickSegment}
                      onSaveMoment={saveTranscriptMoment}
                      onCopyQuote={copyTranscriptQuote}
                    />
                  </>
                ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
