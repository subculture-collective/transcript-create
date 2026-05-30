import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  api,
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
  const playerRef = useRef<YouTubePlayerHandle | null>(null);
  const [showUpgrade, setShowUpgrade] = useState(false);

  const startSeconds = useMemo(() => {
    const tStr = params.get('t');
    const t = tStr ? parseInt(tStr, 10) : 0;
    return Number.isFinite(t) ? t : 0;
  }, [params]);

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
    const q = params.get('q');
    if (q) {
      api
        .search(q, { video_id: videoId })
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
  }, [videoId, params, user]);

  // Scroll to a hash if provided
  useEffect(() => {
    const hash = window.location.hash;
    if (hash) {
      const el = document.querySelector(hash);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [transcript]);

  function jumpTo(ms: number) {
    const s = Math.floor(ms / 1000);
    setParams((prev: URLSearchParams) => {
      const p = new URLSearchParams(prev as unknown as string);
      p.set('t', String(s));
      return p;
    });
    playerRef.current?.seekTo(s, { play: true });
    track({ type: 'seek', payload: { videoId, seconds: s } });
  }

  function onClickSegment(seg: Segment, id: number) {
    setActiveSegId(id);
    jumpTo(seg.start_ms);
    // update hash for deep-linking this segment
    history.replaceState(null, '', `#seg-${id}`);
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
    const seg = transcript?.segments[segId - 1];
    if (seg) jumpTo(seg.start_ms);
  }

  const transcriptTurns = useMemo(
    () => buildTranscriptTurns(transcript?.segments ?? [], hits),
    [transcript?.segments, hits]
  );
  return (
    <div className="space-y-6">
      <header className="surface-card space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="mb-1 text-sm font-medium uppercase tracking-wide text-subtle">Transcript</p>
            <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
              {video?.title ?? 'Loading video...'}
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
            Search within this transcript
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
            placeholder="Search within this transcript…"
            className="form-control"
            aria-label="Search within transcript"
          />
          <button className="btn-primary" type="submit">
            Search transcript
          </button>
        </form>
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
            <h2 className="section-title">Transcript</h2>
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
            <div className="surface-card space-y-6" role="list" aria-label="Formatted transcript paragraphs">
              {formattedBlocks.map((block) => {
                const isFavorite = block.segment_ids.some((segIdx) => favorites.has({ videoId: videoId!, segIndex: segIdx + 1 }));
                const isHighlighted = block.segment_ids.some((segIdx) =>
                  hits?.some((h) => h.start_ms >= transcript.segments[segIdx]?.start_ms && h.start_ms < transcript.segments[segIdx]?.end_ms)
                );
                return (
                  <div
                    key={block.block_index}
                    id={`block-${block.block_index}`}
                    className={block.speaker_label ? 'grid gap-3 sm:grid-cols-[8rem_1fr]' : 'block'}
                    role="listitem"
                  >
                    {block.speaker_label && <div className="font-semibold text-ink">{block.speaker_label}:</div>}
                    <div className="space-y-2 text-lg leading-8 text-ink">
                      <button
                        type="button"
                        onClick={() => jumpTo(block.start_ms)}
                        className={`w-full cursor-pointer rounded px-1 text-left transition-colors hover:bg-surface-muted focus:bg-surface-muted ${
                          isHighlighted ? 'bg-accent-soft ring-1 ring-accent' : ''
                        } ${isFavorite ? 'ring-1 ring-warning' : ''}`}
                        aria-label={`Play ${block.speaker_label ?? 'paragraph'} from ${msToHms(block.start_ms)}`}
                      >
                        {block.text}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="surface-card space-y-6" role="list" aria-label="Transcript paragraphs">
              {transcriptTurns.map((turn) => (
                <div
                  key={turn.key}
                  className={turn.speaker ? 'grid gap-3 sm:grid-cols-[8rem_1fr]' : 'block'}
                  role="listitem"
                >
                  {turn.speaker && <div className="font-semibold text-ink">{turn.speaker}:</div>}
                  <div className="space-y-2 text-lg leading-8 text-ink">
                    <p className="whitespace-normal">
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
                  </div>
                </div>
              ))}
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
