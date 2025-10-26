import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  api,
  apiAddFavorite,
  apiListFavorites,
  apiDeleteFavorite,
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
    playerRef.current?.seekTo(s);
    track({ type: 'seek', payload: { videoId, seconds: s } });
  }

  function onClickSegment(seg: Segment, id: number) {
    setActiveSegId(id);
    jumpTo(seg.start_ms);
    // update hash for deep-linking this segment
    history.replaceState(null, '', `#seg-${id}`);
  }

  function copyLink(segIdx: number, startMs: number) {
    const s = Math.floor(startMs / 1000);
    const url = `${location.origin}/v/${videoId}?t=${s}#seg-${segIdx}`;
    navigator.clipboard?.writeText(url);
  }

  async function toggleFavorite(id: number, seg: Segment) {
    if (!videoId) return;
    if (user) {
      // Check if a server favorite exists for this time range
      const existing = serverFavs.find(
        (f) => f.start_ms === seg.start_ms && f.end_ms === seg.end_ms
      );
      if (existing) {
        await apiDeleteFavorite(existing.id).catch(() => {});
        setServerFavs((prev) => prev.filter((f) => f.id !== existing.id));
        track({
          type: 'favorite_remove',
          payload: { videoId, start_ms: seg.start_ms, end_ms: seg.end_ms },
        });
      } else {
        const res = await apiAddFavorite({
          video_id: videoId,
          start_ms: seg.start_ms,
          end_ms: seg.end_ms,
          text: seg.text,
        }).catch(() => null);
        if (res?.id)
          setServerFavs((prev) => [
            { id: res.id, start_ms: seg.start_ms, end_ms: seg.end_ms },
            ...prev,
          ]);
        track({
          type: 'favorite_add',
          payload: { videoId, start_ms: seg.start_ms, end_ms: seg.end_ms },
        });
      }
    } else {
      favorites.toggle({
        videoId,
        segIndex: id,
        startMs: seg.start_ms,
        endMs: seg.end_ms,
        text: seg.text,
      });
    }
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
  }, [JSON.stringify(matchIndices)]);
  function gotoMatch(direction: 1 | -1) {
    if (matchIndices.length === 0) return;
    const next = (matchCursor + direction + matchIndices.length) % matchIndices.length;
    setMatchCursor(next);
    const segId = matchIndices[next];
    const el = document.getElementById(`seg-${segId}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const seg = transcript?.segments[segId - 1];
    if (seg) jumpTo(seg.start_ms);
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      <div className="lg:col-span-7">
        {video ? (
          <YouTubePlayer
            ref={playerRef}
            videoId={video.youtube_id}
            start={start}
            title={video?.title ?? undefined}
          />
        ) : (
          <div className="aspect-video w-full overflow-hidden rounded-lg border bg-black">
            <div className="flex h-full items-center justify-center text-gray-400" role="status" aria-live="polite">
              <span className="inline-block animate-spin text-3xl mr-3" aria-hidden="true">⟳</span>
              Loading player…
            </div>
          </div>
        )}
        <div className="mt-4 space-y-3">
          <h1 className="text-xl sm:text-2xl font-medium text-stone-900">{video?.title ?? 'Loading video...'}</h1>
          {video && (
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="text-stone-600">Exports:</span>
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
          className="mt-4"
          onSubmit={(e) => {
            e.preventDefault();
          }}
        >
          <label htmlFor="transcript-search" className="sr-only">
            Search within this transcript
          </label>
          <input
            id="transcript-search"
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
            className="w-full rounded-md border border-stone-300 px-3 py-3 focus:border-blue-600 focus:ring-2 focus:ring-blue-600"
            aria-label="Search within transcript"
          />
        </form>
      </div>
      <div className="lg:col-span-5">
        <div className="mb-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h2 className="text-xl font-semibold">Transcript</h2>
          {matchIndices.length > 0 && (
            <div className="flex items-center gap-2 text-sm text-stone-600" role="group" aria-label="Search navigation">
              <button
                className="rounded border border-stone-300 px-3 py-2 hover:bg-stone-50 transition-colors min-h-[44px]"
                onClick={() => gotoMatch(-1)}
                aria-label="Go to previous match"
              >
                Prev
              </button>
              <span aria-live="polite" aria-atomic="true">
                {matchCursor + 1} / {matchIndices.length}
              </span>
              <button
                className="rounded border border-stone-300 px-3 py-2 hover:bg-stone-50 transition-colors min-h-[44px]"
                onClick={() => gotoMatch(1)}
                aria-label="Go to next match"
              >
                Next
              </button>
            </div>
          )}
        </div>
        {!transcript && (
          <div className="text-stone-500 py-8 text-center" role="status" aria-live="polite">
            <span className="inline-block animate-spin text-2xl mb-2" aria-hidden="true">⟳</span>
            <p>Loading transcript…</p>
          </div>
        )}
        {transcript && (
          <ol className="space-y-0.5" role="list" aria-label="Transcript segments">
            {transcript.segments.map((seg, idx) => {
              const id = idx + 1;
              const match = hits?.find(
                (h) => h.start_ms >= seg.start_ms && h.start_ms < seg.end_ms
              );
              const isServerFav = !!serverFavs.find(
                (f) => f.start_ms === seg.start_ms && f.end_ms === seg.end_ms
              );
              return (
                <li
                  id={`seg-${id}`}
                  key={id}
                  className={`group rounded-md px-2 py-2 transition-colors ${activeSegId === id || match ? 'bg-blue-50 ring-1 ring-blue-300' : ''} ${isServerFav || favorites.has({ videoId: videoId!, segIndex: id }) ? 'ring-1 ring-amber-400' : ''}`}
                  role="article"
                  aria-label={`Segment ${id}, timestamp ${msToHms(seg.start_ms)}`}
                >
                  <button 
                    onClick={() => onClickSegment(seg, id)} 
                    className="text-left w-full min-h-[44px]"
                    aria-label={`Play from ${msToHms(seg.start_ms)}`}
                  >
                    <div className="mb-1 text-xs text-stone-500 font-mono">
                      <time dateTime={`PT${Math.floor(seg.start_ms / 1000)}S`}>
                        {msToHms(seg.start_ms)}
                      </time>
                    </div>
                    <p className="font-serif leading-relaxed">{seg.text}</p>
                  </button>
                  <div className="mt-2 hidden items-center gap-3 text-xs text-stone-600 group-hover:flex">
                    <button
                      className="hover:text-stone-900 py-2 transition-colors"
                      onClick={() => copyLink(id, seg.start_ms)}
                      aria-label="Copy link to this segment"
                    >
                      Copy link
                    </button>
                    <button 
                      className="hover:text-stone-900 py-2 transition-colors" 
                      onClick={() => toggleFavorite(id, seg)}
                      aria-label={
                        user
                          ? isServerFav
                            ? 'Remove from saved'
                            : 'Save this segment'
                          : favorites.has({ videoId: videoId!, segIndex: id })
                            ? 'Remove from favorites'
                            : 'Add to favorites'
                      }
                    >
                      {user
                        ? isServerFav
                          ? 'Unsave'
                          : 'Save'
                        : favorites.has({ videoId: videoId!, segIndex: id })
                          ? 'Unfavorite'
                          : 'Favorite'}
                    </button>
                  </div>
                  {match && (
                    <div className="mt-2 rounded bg-yellow-50 p-2 text-xs text-yellow-900" role="note">
                      <div className="mb-1 font-medium">Match</div>
                      <div
                        className="prose prose-xs max-w-none"
                        dangerouslySetInnerHTML={{ __html: match.snippet }}
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
