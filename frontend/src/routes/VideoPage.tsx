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
import { ExportMenu } from '../components';
import type { YouTubePlayerHandle } from '../components/YouTubePlayer';
// track imported from services barrel
import { buildTimestampLink, formatTimestamp } from '../features/archive/format';
import { buildTranscriptTurns, normalizeTranscriptText } from '../features/videoTranscript/transcript';
import {
  FormattedTranscriptDocument,
  PlayerPanel,
  PlainTranscriptTurns,
  TranscriptSearchBar,
  VideoDetailsPanel,
  VideoHeader,
} from '../components/video';

function secondsToYouTubeTs(s: number) {
  return Math.max(0, Math.floor(s));
}

function copyText(text: string) {
  void navigator.clipboard?.writeText(text);
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

  // Scroll/select by explicit hash first. The `t=` URL param is whole-second
  // precision, so using it first can select the previous paragraph for starts
  // like 12.8s. Hashes preserve the exact segment/block identity.
  useEffect(() => {
    const hash = window.location.hash;
    if (hash) {
      const segMatch = hash.match(/^#seg-(\d+)$/);
      if (segMatch) {
        const segId = Number(segMatch[1]);
        const seg = transcript?.segments[segId - 1];
        const block = transcript?.blocks?.find((candidate) => candidate.segment_ids.includes(segId - 1));
        const el = document.getElementById(`seg-${segId}`) ?? (block ? document.getElementById(`block-${block.block_index}`) : null);
        if (seg && el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          setActiveSegId(segId);
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
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          setActiveSegId((block.segment_ids[0] ?? 0) + 1);
          setActiveBlockIndex(block.block_index);
          return;
        }
      }

      const el = document.querySelector(hash);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
    }

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

  function onClickFormattedSentence(segment: Segment, segIndex: number) {
    setActiveSegId(segIndex);
    const blockId = hasFormattedBlocks ? formattedBlocks.find((candidate) => candidate.segment_ids.includes(segIndex - 1))?.block_index : null;
    setActiveBlockIndex(blockId ?? null);
    jumpTo(segment.start_ms);
    history.replaceState(null, '', `#seg-${segIndex}`);
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
  const isSavedSegment = useCallback(
    (segment: Segment, segIndex: number) => {
      if (!videoId) return false;
      return (
        serverFavs.some((favorite) => favorite.start_ms === segment.start_ms && favorite.end_ms === segment.end_ms) ||
        favorites.has({ videoId, segIndex })
      );
    },
    [serverFavs, videoId]
  );
  const episodeTitle = video?.title ?? 'Loading VOD...';
  return (
    <div className="space-y-6">
      <VideoHeader
        title={episodeTitle}
        transcriptSourceLabel={transcript?.source_label}
        transcriptSource={transcript?.source ?? null}
        actions={video ? <ExportMenu videoId={video.id} /> : null}
      >
        <TranscriptSearchBar
          initialQuery={params.get('q') ?? ''}
          onSearch={(value) => {
            const next = new URLSearchParams(params);
            if (value) next.set('q', value);
            else next.delete('q');
            setParams(next);
          }}
        />

        {video && <VideoDetailsPanel video={video} transcriptSource={transcript?.source ?? null} />}
      </VideoHeader>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:items-start">
        <PlayerPanel video={video} start={start} playerRef={playerRef} />

        <section className="lg:col-span-2">
          <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="section-title">VOD transcript</h2>
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
            <FormattedTranscriptDocument
              blocks={formattedBlocks}
              transcriptSegments={transcript.segments}
              hits={hits}
              activeBlockIndex={activeBlockIndex}
              activeSegId={activeSegId}
              isSavedSegment={isSavedSegment}
              onClickSentence={onClickFormattedSentence}
              onSaveMoment={saveTranscriptMoment}
              onCopyQuote={copyTranscriptQuote}
            />
          ) : (
            <PlainTranscriptTurns
              turns={transcriptTurns}
              activeSegId={activeSegId}
              isSavedSegment={isSavedSegment}
              onClickSegment={onClickSegment}
              onSaveMoment={saveTranscriptMoment}
              onCopyQuote={copyTranscriptQuote}
            />
          ))}
        </section>
      </div>
    </div>
  );
}
