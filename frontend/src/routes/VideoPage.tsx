import { useSite } from '../services/site';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import PassagePanel from '../components/video/PassagePanel';
import { buildPassageLink, readPassageRange } from '../features/passages/range';
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
import type {
  ExploreIntelligenceResponse,
  Segment,
  TranscriptResponse,
  VideoInfo,
  SearchHit,
  VideoChapter,
} from '../types/api';
import { ExportMenu } from '../components';
import type { YouTubePlayerHandle } from '../components/YouTubePlayer';
import {
  buildTimestampLink,
  formatDate,
  formatDuration,
  formatTimestamp,
  formatVideoTitle,
} from '../features/archive/format';
import type { TranscriptSource } from '../features/archive/format';
import {
  buildTranscriptTurns,
  normalizeTranscriptText,
} from '../features/videoTranscript/transcript';
import {
  buildProgressiveTranscriptChapters,
  chapterForSegment,
  filterBlocksForChapters,
  filterTurnsForChapters,
  mountedChapterIndexes,
} from '../features/videoTranscript/progressiveChapters';
import { findEpisodeTopics, type TopicCandidate } from '../features/videoTranscript/topics';
import EpisodeNavigator, { type NavigatorTab } from '../components/video/EpisodeNavigator';
import EpisodeStrip, { type StripTick } from '../components/video/EpisodeStrip';
import { visibleOutlineChapters } from '../components/video/EpisodeOutline';
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

// Archive-wide topic cards change slowly; share one request across episodes.
let archiveIntelligenceRequest: Promise<ExploreIntelligenceResponse> | null = null;
function loadArchiveIntelligence() {
  archiveIntelligenceRequest ??= api.getExploreIntelligence().catch((error: unknown) => {
    archiveIntelligenceRequest = null;
    throw error;
  });
  return archiveIntelligenceRequest;
}

function topicCandidates(
  video: VideoInfo | null,
  intelligence: ExploreIntelligenceResponse | null
): TopicCandidate[] {
  const candidates: TopicCandidate[] = [];
  for (const card of intelligence?.topic_cards ?? [])
    candidates.push({
      key: `topic:${card.slug}`,
      label: card.label,
      terms: card.aliases ?? [],
      kind: 'topic',
    });
  for (const tag of video?.tags ?? [])
    candidates.push({ key: `tag:${tag.slug}`, label: tag.label, terms: [], kind: 'tag' });
  for (const person of [...(video?.people ?? []), ...(intelligence?.people ?? [])])
    candidates.push({
      key: `person:${person.slug}`,
      label: person.display_name,
      terms: person.aliases ?? [],
      kind: 'person',
    });
  for (const tag of intelligence?.tags ?? [])
    candidates.push({ key: `tag:${tag.slug}`, label: tag.label, terms: [], kind: 'tag' });
  for (const search of [
    ...(intelligence?.trending_searches ?? []),
    ...(intelligence?.suggested_searches ?? []),
    ...(intelligence?.summary?.popular_searches ?? []),
  ])
    candidates.push({
      key: `search:${search.term.toLowerCase()}`,
      label: search.term,
      terms: [],
      kind: 'search',
    });
  return candidates;
}

export default function VideoPage() {
  const site = useSite();
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
    Array<{ id: string; start_ms: number; end_ms: number; text?: string }>
  >([]);
  const [localFavoritesVersion, setLocalFavoritesVersion] = useState(0);
  const [intelligence, setIntelligence] = useState<ExploreIntelligenceResponse | null>(null);
  const [intelligenceStatus, setIntelligenceStatus] = useState<'loading' | 'ready' | 'error'>(
    'loading'
  );
  const [activeTopicKey, setActiveTopicKey] = useState<string | null>(null);
  const [activeSegId, setActiveSegId] = useState<number | null>(null);
  const [activeSentenceId, setActiveSentenceId] = useState<string | null>(null);
  const [activeBlockIndex, setActiveBlockIndex] = useState<number | null>(null);
  const [activeTranscriptChapter, setActiveTranscriptChapter] = useState(0);
  const [fullTranscript, setFullTranscript] = useState(false);
  const [viewMode, setViewMode] = useState<'standard' | 'theater' | 'reader'>('standard');
  const [isPlayingMatches, setIsPlayingMatches] = useState(false);
  const [autoFollowEnabled, setAutoFollowEnabled] = useState(true);
  const [operationFeedback, setOperationFeedback] = useState<string | null>(null);
  const [isMobileEpisode, setIsMobileEpisode] = useState(() =>
    typeof window === 'undefined' ? false : window.matchMedia?.('(max-width: 1023px)').matches
  );
  const [mobileTab, setMobileTab] = useState<'transcript' | 'chapters' | 'topics' | 'info'>(
    'transcript'
  );
  const [sheetSnap, setSheetSnap] = useState<'collapsed' | 'half' | 'expanded'>('half');
  const playerRef = useRef<YouTubePlayerHandle | null>(null);
  const autoFollowScrollTimeoutRef = useRef<number | null>(null);
  const sheetDragStartRef = useRef<number | null>(null);

  useEffect(() => {
    const query = window.matchMedia?.('(max-width: 1023px)');
    if (!query) return;
    const update = () => setIsMobileEpisode(query.matches);
    update();
    query.addEventListener?.('change', update);
    return () => query.removeEventListener?.('change', update);
  }, []);

  const changeSheetSnap = useCallback((direction: -1 | 1) => {
    const snaps = ['collapsed', 'half', 'expanded'] as const;
    setSheetSnap((current) => {
      const index = snaps.indexOf(current);
      return snaps[Math.max(0, Math.min(snaps.length - 1, index + direction))];
    });
  }, []);

  useEffect(() => {
    let active = true;
    setIntelligenceStatus('loading');
    loadArchiveIntelligence()
      .then((response) => {
        if (!active) return;
        setIntelligence(response);
        setIntelligenceStatus('ready');
      })
      .catch(() => {
        if (active) setIntelligenceStatus('error');
      });
    return () => {
      active = false;
    };
  }, []);

  const closeSelection = useCallback(() => {
    setActiveSegId(null);
    setActiveSentenceId(null);
    setActiveBlockIndex(null);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (document.querySelector('.transcript-block[data-open="true"]')) closeSelection();
      else if (isMobileEpisode) setSheetSnap('collapsed');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [closeSelection, isMobileEpisode]);

  const startMilliseconds = useMemo(() => {
    const exact = params.get('t_ms');
    if (exact) {
      const parsed = Number(exact);
      if (Number.isFinite(parsed) && parsed >= 0) return Math.floor(parsed);
    }
    const tStr = params.get('t');
    const t = tStr ? Number(tStr) : 0;
    return Number.isFinite(t) && t >= 0 ? Math.floor(t * 1000) : 0;
  }, [params]);
  const passageRange = readPassageRange(params);
  const startSeconds = Math.floor(startMilliseconds / 1000);
  function sharePassage(segment: Segment) {
    setIsPlayingMatches(false);
    playerRef.current?.pause();
    const url = new URL(
      buildPassageLink(videoId!, { startMs: segment.start_ms, endMs: segment.end_ms }),
      window.location.origin
    );
    setParams(url.searchParams);
  }
  function closePassage() {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.delete('end_ms');
      return next;
    });
  }
  const requestedTranscriptSource = useMemo(() => {
    const source = params.get('source');
    if (source === 'whisper' || source === 'youtube' || source === 'merged') return source;
    const hashSource = window.location.hash.match(/^#moment-(whisper|youtube|merged)-\d+$/)?.[1];
    return hashSource === 'whisper' || hashSource === 'youtube' || hashSource === 'merged'
      ? hashSource
      : null;
  }, [params]);
  const normalizeMomentUrl = useCallback((startMs: number) => {
    const url = new URL(window.location.href, 'http://localhost');
    url.searchParams.delete('source');
    url.searchParams.set('t', String(Math.floor(startMs / 1000)));
    if (startMs % 1000) url.searchParams.set('t_ms', String(startMs));
    else url.searchParams.delete('t_ms');
    url.hash = `moment-${startMs}`;
    history.replaceState(null, '', `${url.pathname}?${url.searchParams.toString()}${url.hash}`);
  }, []);
  const transcriptQuery = useMemo(() => params.get('q') ?? '', [params]);

  const scrollElementIntoView = useCallback(
    (element: Element | null, options?: ScrollIntoViewOptions) => {
      if (!element || params.has('end_ms')) return;
      if (autoFollowScrollTimeoutRef.current != null) {
        window.clearTimeout(autoFollowScrollTimeoutRef.current);
      }
      autoFollowScrollTimeoutRef.current = window.setTimeout(() => {
        autoFollowScrollTimeoutRef.current = null;
      }, 1000);
      element.scrollIntoView(options ?? { behavior: 'smooth', block: 'center' });
    },
    [params]
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
    async (id: string, source: 'best' | TranscriptSource = 'best') => {
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
        void loadTranscript(
          videoId,
          requestedTranscriptSource ?? (response.has_whisper_transcript ? 'whisper' : 'best')
        );
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
  }, [loadTranscript, requestedTranscriptSource, videoId]);

  useEffect(() => {
    if (!video) return;
    document.title = `${formatVideoTitle(video.title, video.uploaded_at)} | ${site.name}`;
  }, [video, site.name]);

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
            text: i.text,
          }));
          setServerFavs(filtered);
        })
        .catch(() => setServerFavs([]));
    } else {
      setServerFavs([]);
    }
  }, [user, videoId]);

  const formattedBlocks = useMemo(
    () => transcript?.blocks?.filter((block) => block.text.trim()) ?? [],
    [transcript?.blocks]
  );
  const hasFormattedBlocks = formattedBlocks.length > 0;
  const transcriptChapters = useMemo(
    () => buildProgressiveTranscriptChapters(transcript?.segments ?? [], chapters),
    [chapters, transcript?.segments]
  );
  const mountedTranscriptChapters = useMemo(
    () =>
      fullTranscript
        ? transcriptChapters.map((chapter) => chapter.index)
        : mountedChapterIndexes(activeTranscriptChapter, transcriptChapters.length),
    [activeTranscriptChapter, fullTranscript, transcriptChapters]
  );
  const visibleFormattedBlocks = useMemo(
    () => filterBlocksForChapters(formattedBlocks, transcriptChapters, mountedTranscriptChapters),
    [formattedBlocks, mountedTranscriptChapters, transcriptChapters]
  );

  const mountSegmentChapter = useCallback(
    (segmentIndex: number) => {
      if (fullTranscript) return false;
      const chapterIndex = chapterForSegment(transcriptChapters, segmentIndex);
      if (chapterIndex < 0 || chapterIndex === activeTranscriptChapter) return false;
      setActiveTranscriptChapter(chapterIndex);
      return true;
    },
    [activeTranscriptChapter, fullTranscript, transcriptChapters]
  );

  useEffect(() => {
    setActiveTranscriptChapter(0);
    setFullTranscript(false);
  }, [videoId]);

  // Reading past the last mounted section brings in the next one, so the
  // transcript reads as one continuous document.
  const continueReadingRef = useRef<HTMLDivElement | null>(null);
  const lastMountedChapter = mountedTranscriptChapters.at(-1) ?? 0;
  useEffect(() => {
    const element = continueReadingRef.current;
    if (!element || typeof IntersectionObserver === 'undefined' || fullTranscript) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setActiveTranscriptChapter((current) =>
          Math.min(transcriptChapters.length - 1, Math.max(current, lastMountedChapter))
        );
      },
      { rootMargin: '0px 0px 400px 0px' }
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [fullTranscript, lastMountedChapter, transcriptChapters.length, transcriptStatus]);

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
      const canonicalMatch = hash.match(/^#moment-(?:(whisper|youtube|merged)-)?(\d+)$/);
      if (canonicalMatch && transcript) {
        const targetMs = Number(canonicalMatch[2]);
        const segIndex = transcript.segments.findIndex((seg) => seg.start_ms === targetMs);
        if (segIndex >= 0) {
          if (mountSegmentChapter(segIndex)) return;
          const target = document.getElementById(hash.slice(1));
          if (target) {
            scrollElementIntoView(target, { behavior: 'smooth', block: 'center' });
            setActiveSegId(segIndex + 1);
            setActiveSentenceId(null);
            if (canonicalMatch[1] || params.has('source')) normalizeMomentUrl(targetMs);
            return;
          }
        }
      }

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
        if (seg && mountSegmentChapter(segId - 1)) return;
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
          if (!sentenceSuffix) normalizeMomentUrl(seg.start_ms);
          return;
        }
      }

      const blockMatch = hash.match(/^#block-(\d+)$/);
      if (blockMatch) {
        const blockIndex = Number(blockMatch[1]);
        const block = transcript?.blocks?.find((candidate) => candidate.block_index === blockIndex);
        const firstSegment = block?.segment_ids[0];
        if (firstSegment != null && mountSegmentChapter(firstSegment)) return;
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

    if (transcript && startMilliseconds > 0) {
      const startMs = startMilliseconds;
      let segIndex = transcript.segments.findIndex(
        (seg) => startMs >= seg.start_ms && startMs < seg.end_ms
      );
      if (segIndex < 0) {
        segIndex = transcript.segments.findIndex(
          (seg) => seg.start_ms >= startMs && seg.start_ms < startMs + 1000
        );
      }
      if (segIndex >= 0) {
        if (mountSegmentChapter(segIndex)) return;
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
          if (params.has('source')) normalizeMomentUrl(transcript.segments[segIndex].start_ms);
          return;
        }
      }
    }
  }, [
    activeTranscriptChapter,
    mountSegmentChapter,
    normalizeMomentUrl,
    params,
    scrollElementIntoView,
    startMilliseconds,
    transcript,
  ]);

  const jumpTo = useCallback(
    (ms: number) => {
      const s = Math.floor(ms / 1000);
      setParams((prev: URLSearchParams) => {
        const p = new URLSearchParams(prev as unknown as string);
        p.delete('end_ms');
        p.set('t', String(s));
        if (ms % 1000 !== 0) p.set('t_ms', String(Math.max(0, Math.floor(ms))));
        else p.delete('t_ms');
        return p;
      });
      playerRef.current?.seekTo(s, { play: true });
      track({ type: 'seek', payload: { videoId, seconds: s } });
    },
    [setParams, videoId]
  );

  // Selecting a passage opens its actions; playback starts only on request.
  function onClickSegment(_seg: Segment, id: number) {
    mountSegmentChapter(id - 1);
    setActiveSegId(id);
    setActiveSentenceId(null);
    setActiveBlockIndex(null);
    history.replaceState(null, '', `#seg-${id}`);
  }

  function playFromSegment(seg: Segment, id: number) {
    onClickSegment(seg, id);
    jumpTo(seg.start_ms);
  }

  function onClickFormattedSentence(_segment: Segment, segIndex: number, sentenceId: string) {
    mountSegmentChapter(segIndex - 1);
    setActiveSegId(segIndex);
    setActiveSentenceId(sentenceId);
    const blockId = hasFormattedBlocks
      ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(segIndex - 1))
          ?.block_index
      : null;
    setActiveBlockIndex(blockId ?? null);
    const sentenceSuffix = sentenceId.split('-s-').at(1);
    history.replaceState(
      null,
      '',
      sentenceSuffix ? `#seg-${segIndex}-s-${sentenceSuffix}` : `#seg-${segIndex}`
    );
  }

  function playFromSentence(segment: Segment, segIndex: number, sentenceId: string) {
    onClickFormattedSentence(segment, segIndex, sentenceId);
    jumpTo(segment.start_ms);
  }

  /** Select and reveal the passage containing `ms` without starting playback. */
  function openMomentAt(ms: number) {
    const segments = transcript?.segments ?? [];
    let segIndex = segments.findIndex((seg) => ms >= seg.start_ms && ms < seg.end_ms);
    if (segIndex < 0) segIndex = segments.findIndex((seg) => seg.start_ms >= ms);
    if (segIndex < 0) return;
    setAutoFollowEnabled(false);
    // Keep the URL hash in step so a chapter remount reselects this passage.
    history.replaceState(null, '', `#moment-${segments[segIndex].start_ms}`);
    mountSegmentChapter(segIndex);
    const block = hasFormattedBlocks
      ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(segIndex))
      : undefined;
    setActiveSegId(segIndex + 1);
    setActiveSentenceId(null);
    setActiveBlockIndex(block?.block_index ?? null);
    if (isMobileEpisode) setMobileTab('transcript');
    window.setTimeout(() => {
      const element =
        (block ? document.getElementById(`block-${block.block_index}`) : null) ??
        document.getElementById(`seg-${segIndex + 1}`);
      element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 60);
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
  const [matchCursor, setMatchCursor] = useState(0);
  useEffect(() => {
    setMatchCursor(0);
  }, [matchIndices]);

  useEffect(() => {
    if (params.get('play') !== 'matches' || matchIndices.length === 0 || !transcript) return;
    const startMs = startMilliseconds;
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
  }, [matchIndices, params, startMilliseconds, transcript]);
  function gotoMatch(direction: 1 | -1) {
    if (matchIndices.length === 0) return;
    const next = (matchCursor + direction + matchIndices.length) % matchIndices.length;
    setMatchCursor(next);
    const segId = matchIndices[next];
    mountSegmentChapter(segId - 1);
    const blockId = hasFormattedBlocks
      ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(segId - 1))?.block_index
      : null;
    window.setTimeout(() => {
      const el =
        blockId !== null
          ? document.getElementById(`block-${blockId}`)
          : document.getElementById(`seg-${segId}`);
      if (el) scrollElementIntoView(el, { behavior: 'smooth', block: 'center' });
    }, 0);
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
      mountSegmentChapter(nextSegId - 1);
      const blockId = hasFormattedBlocks
        ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(nextSegId - 1))
            ?.block_index
        : null;
      window.setTimeout(() => {
        const el =
          blockId !== null
            ? document.getElementById(`block-${blockId}`)
            : document.getElementById(`seg-${nextSegId}`);
        if (el) scrollElementIntoView(el, { behavior: 'smooth', block: 'center' });
      }, 0);
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
    mountSegmentChapter,
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
          { id: created.id, start_ms: segment.start_ms, end_ms: segment.end_ms, text },
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
          source: transcript?.source,
        });
        track({
          type: wasSaved ? 'favorite_remove' : 'favorite_add',
          payload: { videoId, start_ms: segment.start_ms },
        });
        setLocalFavoritesVersion((version) => version + 1);
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

  async function copyTranscriptLink(segment: Segment, segIndex: number) {
    if (!videoId) return;
    try {
      await copyText(
        `${window.location.origin}${buildTimestampLink(videoId, segment.start_ms, segIndex)}`
      );
      setOperationFeedback('Link to this moment copied.');
    } catch {
      setOperationFeedback('The link could not be copied.');
    }
  }

  const episodeTopics = useMemo(
    () => findEpisodeTopics(transcript?.segments ?? [], topicCandidates(video, intelligence)),
    [intelligence, transcript?.segments, video]
  );
  const activeTopic = episodeTopics.find((topic) => topic.key === activeTopicKey) ?? null;
  const outlineChapters = useMemo(() => visibleOutlineChapters(chapters), [chapters]);
  const durationMs =
    (video?.duration_seconds ?? 0) * 1000 ||
    (transcript?.segments.length ? transcript.segments[transcript.segments.length - 1].end_ms : 0);
  const stripTicks = useMemo<StripTick[]>(() => {
    if (activeTopic)
      return activeTopic.mentions.map((mention) => ({ ms: mention.startMs, kind: 'topic' }));
    return (hits ?? []).map((hit) => ({ ms: hit.start_ms, kind: 'match' }));
  }, [activeTopic, hits]);
  const savedMoments = useMemo(() => {
    void localFavoritesVersion;
    if (!videoId) return [];
    const local = favorites
      .list()
      .filter((item) => item.videoId === videoId)
      .map((item) => ({ startMs: item.startMs, text: item.text }));
    const server = serverFavs.map((item) => ({ startMs: item.start_ms, text: item.text ?? '' }));
    const byStart = new Map([...local, ...server].map((item) => [item.startMs, item]));
    return [...byStart.values()].sort((left, right) => left.startMs - right.startMs);
  }, [localFavoritesVersion, serverFavs, videoId]);

  function highlightTopic(label: string) {
    const next = new URLSearchParams(params);
    next.set('q', label);
    setParams(next);
    setAutoFollowEnabled(false);
  }

  const transcriptTurns = useMemo(
    () => buildTranscriptTurns(transcript?.segments ?? [], hits),
    [transcript?.segments, hits]
  );
  const visibleTranscriptTurns = useMemo(
    () => filterTurnsForChapters(transcriptTurns, transcriptChapters, mountedTranscriptChapters),
    [mountedTranscriptChapters, transcriptChapters, transcriptTurns]
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
    document.title = `${episodeTitle} | ${site.name}`;
  }, [episodeTitle, video, site.name]);

  function selectChapter(chapter: VideoChapter) {
    const segmentIndex = transcript?.segments.findIndex(
      (segment) => segment.start_ms >= chapter.start_ms
    );
    if (segmentIndex != null && segmentIndex >= 0) mountSegmentChapter(segmentIndex);
    jumpTo(chapter.start_ms);
    setAutoFollowEnabled(true);
    window.setTimeout(() => {
      const evidence = chapter.evidence[0];
      const target =
        document.getElementById(`chapter-${chapter.chapter_index}`) ??
        (evidence ? document.getElementById(`block-${evidence.block_index}`) : null);
      scrollElementIntoView(target, { behavior: 'smooth', block: 'start' });
    }, 60);
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
  const transcriptSource = (transcript?.source ?? 'whisper') as TranscriptSource;
  const showProgressiveControls = !fullTranscript && transcriptChapters.length > 1;

  const renderNavigator = (currentMs: number | null, fixedTab?: NavigatorTab) =>
    video ? (
      <EpisodeNavigator
        key={fixedTab ?? 'rail'}
        videoId={video.id}
        durationMs={durationMs}
        chapters={outlineChapters}
        currentMs={currentMs}
        onSelectChapter={(chapter) => {
          selectChapter(chapter);
          if (isMobileEpisode) setMobileTab('transcript');
        }}
        topics={episodeTopics}
        topicsLoading={intelligenceStatus === 'loading' || transcriptStatus === 'loading'}
        activeTopicKey={activeTopicKey}
        onToggleTopic={setActiveTopicKey}
        onHighlightTopic={(topic) => {
          highlightTopic(topic.label);
          if (isMobileEpisode) setMobileTab('transcript');
        }}
        onOpenMoment={openMomentAt}
        savedMoments={savedMoments}
        fixedTab={fixedTab}
      />
    ) : null;

  const playbackSync = (
    <PlaybackProgress
      chapters={chapters}
      onSelectChapter={selectChapter}
      playerRef={playerRef}
      transcriptKey={`${videoId}:${transcript?.segments.length ?? 0}:${formattedBlocks.length}:${mountedTranscriptChapters.join(',')}:${mobileTab}:${viewMode}`}
      autoFollow={autoFollowEnabled}
      onAutoScroll={autoScrollToPlayback}
      onPlaybackTime={(currentMs) => {
        const segmentIndex = transcript?.segments.findIndex(
          (segment) => currentMs >= segment.start_ms && currentMs < segment.end_ms
        );
        if (segmentIndex != null && segmentIndex >= 0 && autoFollowEnabled)
          mountSegmentChapter(segmentIndex);
      }}
    >
      {(currentMs) =>
        isMobileEpisode ? (
          (mobileTab === 'chapters' || mobileTab === 'topics') && (
            <div className="mobile-sheet-panel">{renderNavigator(currentMs, mobileTab)}</div>
          )
        ) : (
          <>
            {video && (
              <EpisodeStrip
                durationMs={durationMs}
                chapters={outlineChapters}
                currentMs={currentMs}
                ticks={stripTicks}
                onSeek={(ms) => {
                  setAutoFollowEnabled(true);
                  jumpTo(ms);
                }}
              />
            )}
            {renderNavigator(currentMs)}
          </>
        )
      }
    </PlaybackProgress>
  );

  const progressiveNav = transcriptChapters.length > 1 && (
    <nav className="transcript-sections" aria-label="Transcript sections">
      <span className="mr-auto" role="status" aria-live="polite">
        Section {activeTranscriptChapter + 1} of {transcriptChapters.length}
      </span>
      {showProgressiveControls && (
        <>
          <button
            type="button"
            className="toolbar-button"
            disabled={activeTranscriptChapter === 0}
            onClick={() => setActiveTranscriptChapter((current) => Math.max(0, current - 1))}
          >
            Previous section
          </button>
          <button
            type="button"
            className="toolbar-button"
            disabled={activeTranscriptChapter >= transcriptChapters.length - 1}
            onClick={() =>
              setActiveTranscriptChapter((current) =>
                Math.min(transcriptChapters.length - 1, current + 1)
              )
            }
          >
            Next section
          </button>
        </>
      )}
      <button
        type="button"
        className="toolbar-button"
        aria-description="Full-document mode may reduce performance on long transcripts."
        onClick={() => setFullTranscript((current) => !current)}
      >
        {fullTranscript ? 'Use progressive transcript' : 'Load full transcript'}
      </button>
    </nav>
  );

  const nextSection = transcriptChapters[lastMountedChapter + 1];
  const continueReading = showProgressiveControls && nextSection && (
    <div className="transcript-pager" ref={continueReadingRef}>
      <span>
        Continue reading from{' '}
        <strong className="font-mono text-ink">{formatTimestamp(nextSection.startMs)}</strong>
      </span>
      <button
        type="button"
        className="toolbar-button toolbar-button-accent"
        onClick={() => setActiveTranscriptChapter(nextSection.index)}
      >
        Keep reading ↓
      </button>
    </div>
  );

  return (
    <div className="episode-page">
      {video && isMobileEpisode && (
        <div className="mobile-player-dock" id="episode-player">
          <PlayerPanel video={video} start={start} playerRef={playerRef} />
        </div>
      )}
      <VideoHeader
        title={episodeTitle}
        facts={
          video ? (
            <>
              <span className="font-medium text-ink">
                {video.channel_name || 'Unknown channel'}
              </span>
              {video.uploaded_at && <span>{formatDate(video.uploaded_at)}</span>}
              {video.duration_seconds ? (
                <span className="font-mono text-[13px]">
                  {formatDuration(video.duration_seconds)}
                </span>
              ) : null}
              {transcript && (
                <span>{transcript.segments.length.toLocaleString()} transcript segments</span>
              )}
            </>
          ) : null
        }
        actions={
          video ? (
            <>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  const key = 'hasanara:saved-episodes';
                  const saved = new Set<string>(JSON.parse(localStorage.getItem(key) ?? '[]'));
                  saved.add(video.id);
                  localStorage.setItem(key, JSON.stringify([...saved]));
                  setOperationFeedback('Episode saved on this device.');
                }}
              >
                Save
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() =>
                  void copyText(window.location.href)
                    .then(() => setOperationFeedback('Episode link copied.'))
                    .catch(() =>
                      setOperationFeedback(
                        'The episode link could not be copied. Copy the address from your browser.'
                      )
                    )
                }
              >
                Share
              </button>
              <ExportMenu videoId={video.id} />
              <a
                className="btn-secondary"
                href={`https://www.youtube.com/watch?v=${video.youtube_id}`}
                target="_blank"
                rel="noreferrer"
              >
                YouTube
              </a>
            </>
          ) : null
        }
      >
        {video && (video.people?.length || video.tags?.length) ? (
          <VideoDetailsPanel video={video} />
        ) : null}
      </VideoHeader>
      {video && passageRange && (
        <PassagePanel
          key={`${videoId}:${params.get('t_ms') ?? params.get('t')}:${params.get('end_ms')}`}
          videoId={video.id}
          title={episodeTitle}
          initialRange={passageRange}
          durationMs={video.duration_seconds ? video.duration_seconds * 1000 : undefined}
          segments={transcript?.segments ?? []}
          playerRef={playerRef}
          onClose={closePassage}
          onShowPlayer={() => {
            if (viewMode === 'reader') setViewMode('standard');
            if (!isMobileEpisode)
              requestAnimationFrame(() =>
                document
                  .getElementById('episode-player')
                  ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
              );
          }}
        />
      )}
      {operationFeedback && (
        <div className="mb-4 text-sm text-success" role="status">
          {operationFeedback}
        </div>
      )}

      <div className={viewMode === 'standard' ? 'transcript-layout' : 'space-y-6'}>
        <aside
          aria-label="Player and episode navigator"
          className={
            viewMode === 'standard'
              ? 'transcript-rail'
              : viewMode === 'theater'
                ? 'mx-auto max-w-6xl space-y-4'
                : 'hidden'
          }
        >
          {video && !isMobileEpisode && (
            <div id="episode-player">
              <PlayerPanel video={video} start={start} playerRef={playerRef} />
            </div>
          )}
          {!isMobileEpisode && playbackSync}
        </aside>

        <section
          className={`${viewMode === 'standard' ? 'min-w-0' : 'mx-auto max-w-5xl'} mobile-transcript-sheet`}
          aria-labelledby="transcript-title"
          aria-expanded={sheetSnap === 'expanded'}
          aria-label={`${sheetSnap} episode reader`}
          data-snap={sheetSnap}
        >
          {isMobileEpisode && (
            <div className="mobile-sheet-controls">
              <button
                type="button"
                className="mobile-sheet-handle"
                aria-label={`${sheetSnap} transcript sheet. Use arrow keys or drag to resize.`}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowUp') changeSheetSnap(1);
                  if (event.key === 'ArrowDown') changeSheetSnap(-1);
                }}
                onPointerDown={(event) => {
                  sheetDragStartRef.current = event.clientY;
                  event.currentTarget.setPointerCapture(event.pointerId);
                }}
                onPointerUp={(event) => {
                  const startY = sheetDragStartRef.current;
                  sheetDragStartRef.current = null;
                  if (startY == null) return;
                  const delta = event.clientY - startY;
                  if (delta < -42) changeSheetSnap(1);
                  if (delta > 42) changeSheetSnap(-1);
                }}
              >
                <span aria-hidden="true" />
              </button>
              <div className="mobile-sheet-tabs" role="tablist" aria-label="Episode reader">
                {(['transcript', 'chapters', 'topics', 'info'] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    role="tab"
                    aria-selected={mobileTab === tab}
                    onClick={() => {
                      setMobileTab(tab);
                      if (sheetSnap === 'collapsed') setSheetSnap('half');
                    }}
                  >
                    {tab[0].toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>
              <div className="mobile-sheet-snap-actions">
                <button
                  type="button"
                  onClick={() => changeSheetSnap(-1)}
                  disabled={sheetSnap === 'collapsed'}
                >
                  Collapse
                </button>
                <span className="sr-only" role="status" aria-live="polite">
                  Transcript sheet {sheetSnap}
                </span>
                <button
                  type="button"
                  onClick={() => changeSheetSnap(1)}
                  disabled={sheetSnap === 'expanded'}
                >
                  Expand
                </button>
              </div>
            </div>
          )}
          {isMobileEpisode && playbackSync}
          {(!isMobileEpisode || mobileTab === 'transcript') && (
            <div className="transcript-shell">
              <header className="transcript-toolbar">
                <h2 id="transcript-title" className="sr-only">
                  Transcript
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="min-w-[14rem] flex-1">
                    <TranscriptSearchBar
                      initialQuery={params.get('q') ?? ''}
                      onSearch={(value) => {
                        const next = new URLSearchParams(params);
                        if (value) next.set('q', value);
                        else next.delete('q');
                        setParams(next);
                      }}
                    />
                  </div>
                  {matchIndices.length > 0 && (
                    <div
                      className="flex items-center gap-1.5"
                      role="group"
                      aria-label="Search navigation"
                    >
                      <span
                        className="min-w-14 text-center font-mono text-xs text-muted"
                        aria-live="polite"
                        aria-atomic="true"
                      >
                        {matchCursor + 1} / {matchIndices.length}
                      </span>
                      <button
                        type="button"
                        className="toolbar-button"
                        onClick={() => gotoMatch(-1)}
                        aria-label="Go to previous match"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="toolbar-button"
                        onClick={() => gotoMatch(1)}
                        aria-label="Go to next match"
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="toolbar-button"
                        onClick={() => setIsPlayingMatches((value) => !value)}
                        aria-label="Play all matching transcript moments"
                      >
                        {isPlayingMatches ? 'Stop' : 'Play matches'}
                      </button>
                    </div>
                  )}
                  <div className="flex items-center gap-2">
                    {autoFollowEnabled ? (
                      <span
                        className="inline-flex min-h-11 items-center gap-2 px-2 text-xs font-semibold text-accent"
                        role="status"
                      >
                        <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
                        Following live transcript
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="follow-live-button"
                        onClick={resumeAutoFollow}
                      >
                        <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
                        Enable follow live
                      </button>
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
                    {!isMobileEpisode && (
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
                    )}
                  </div>
                </div>
              </header>

              <div className="transcript-body">
                {transcriptStatus === 'loading' && (
                  <div className="py-24 text-center text-muted" role="status" aria-live="polite">
                    <span
                      className="mb-4 inline-block h-7 w-7 animate-spin rounded-full border-2 border-border border-t-accent"
                      aria-hidden="true"
                    />
                    <p className="text-sm">Loading transcript…</p>
                  </div>
                )}
                {transcriptStatus === 'error' && (
                  <div className="mx-auto max-w-lg px-6 py-24 text-center" role="alert">
                    <h3 className="text-lg font-semibold text-ink">
                      Transcript took too long to load
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-muted">
                      The source transcript is still available. Try the request again without
                      leaving this episode.
                    </p>
                    <button
                      type="button"
                      className="btn-primary mt-5"
                      onClick={() =>
                        videoId &&
                        void loadTranscript(
                          videoId,
                          requestedTranscriptSource ??
                            (video?.has_whisper_transcript ? 'whisper' : 'best')
                        )
                      }
                    >
                      Try again
                    </button>
                  </div>
                )}
                {transcriptStatus === 'ready' && transcript && (
                  <>
                    <TranscriptQualityNotice
                      source={transcriptSource}
                      sourceLabel={transcript.source_label}
                      blocks={hasFormattedBlocks ? formattedBlocks : []}
                    />
                    {progressiveNav}
                    {hasFormattedBlocks ? (
                      <FormattedTranscriptDocument
                        source={transcriptSource}
                        blocks={visibleFormattedBlocks}
                        transcriptSegments={transcript.segments}
                        hits={hits}
                        chapters={outlineChapters}
                        activeBlockIndex={activeBlockIndex}
                        activeSegId={activeSegId}
                        activeSentenceId={activeSentenceId}
                        isSavedSegment={isSavedSegment}
                        onClickSentence={onClickFormattedSentence}
                        onPlayFrom={playFromSentence}
                        onCloseSelection={closeSelection}
                        onSaveMoment={saveTranscriptMoment}
                        onCopyQuote={copyTranscriptQuote}
                        onCopyLink={copyTranscriptLink}
                        onSharePassage={sharePassage}
                      />
                    ) : (
                      <PlainTranscriptTurns
                        turns={visibleTranscriptTurns}
                        source={transcriptSource}
                        activeSegId={activeSegId}
                        isSavedSegment={isSavedSegment}
                        onClickSegment={onClickSegment}
                        onPlayFrom={playFromSegment}
                        onCloseSelection={closeSelection}
                        onSaveMoment={saveTranscriptMoment}
                        onCopyQuote={copyTranscriptQuote}
                        onCopyLink={copyTranscriptLink}
                        onSharePassage={sharePassage}
                      />
                    )}
                    {continueReading}
                  </>
                )}
              </div>
            </div>
          )}
          {isMobileEpisode && mobileTab === 'info' && video && (
            <div className="mobile-sheet-panel space-y-5">
              <h2 className="section-title">Episode information</h2>
              <VideoDetailsPanel video={video} />
              <EpisodeIntelligence videoId={video.id} />
              <ExportMenu videoId={video.id} />
              <a
                className="btn-secondary w-full"
                href={`https://www.youtube.com/watch?v=${video.youtube_id}`}
                target="_blank"
                rel="noreferrer"
              >
                Open source on YouTube
              </a>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
