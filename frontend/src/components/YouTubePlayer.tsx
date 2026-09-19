import { useCallback, useEffect, useImperativeHandle, useRef, useState, forwardRef } from 'react';
import { loadYouTubeApi } from '../services/youtubeApi';

type YouTubePlayer = {
  destroy?: () => void;
  loadVideoById?: (options: { videoId: string; startSeconds: number; endSeconds?: number }) => void;
  seekTo?: (seconds: number, allowSeekAhead: boolean) => void;
  playVideo?: () => void;
  pauseVideo?: () => void;
  getPlayerState?: () => number;
  getCurrentTime?: () => number;
};

type YouTubePlayerConstructor = {
  new (
    element: HTMLElement,
    config: {
      height: string;
      width: string;
      videoId: string;
      playerVars: { start: number; autoplay: number };
      events: { onReady: () => void; onError: (event: { data?: number }) => void };
    }
  ): YouTubePlayer;
};

declare global {
  interface Window {
    YT?: {
      Player?: YouTubePlayerConstructor;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

export type YouTubePlayerHandle = {
  seekTo: (seconds: number, options?: { play?: boolean }) => void;
  play: () => void;
  pause: () => void;
  togglePlay: () => void;
  getCurrentTime: () => number | null;
  previewRange: (startSeconds: number, endSeconds: number) => void;
};

type Props = { videoId: string; start?: number; title?: string };

const YOUTUBE_PLAYING_STATE = 1;

export default forwardRef<YouTubePlayerHandle, Props>(function YouTubePlayer(
  { videoId, start = 0, title },
  ref
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<YouTubePlayer | null>(null);
  const startRef = useRef(start);
  const previousStartRef = useRef(start);
  startRef.current = start;
  const pendingSeekRef = useRef<{ seconds: number; play: boolean } | null>(null);
  const pendingRangeRef = useRef<{ startSeconds: number; endSeconds: number } | null>(null);
  const [ready, setReady] = useState(false);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const seek = useCallback(
    (seconds: number, play = false) => {
      pendingRangeRef.current = null;
      pendingSeekRef.current = { seconds, play };
      if (!ready || !playerRef.current) return;
      try {
        playerRef.current.seekTo?.(seconds, true);
        const isPlaying = playerRef.current.getPlayerState?.() === YOUTUBE_PLAYING_STATE;
        if (play && !isPlaying) playerRef.current.playVideo?.();
        pendingSeekRef.current = null;
      } catch {
        // Suppress errors during seek; keep pending seek for the next ready transition
      }
    },
    [ready]
  );

  useEffect(() => {
    let active = true;
    setReady(false);
    setScriptError(null);
    pendingRangeRef.current = null;
    const initialStart = startRef.current;
    pendingSeekRef.current = initialStart ? { seconds: initialStart, play: false } : null;
    void loadYouTubeApi()
      .then(() => {
        if (!active || !containerRef.current || !window.YT?.Player) return;
        playerRef.current = new window.YT.Player(containerRef.current, {
          height: '100%',
          width: '100%',
          videoId,
          playerVars: { start: initialStart, autoplay: 0 },
          events: {
            onReady: () => {
              if (active) setReady(true);
            },
            onError: (event) => {
              if (active)
                setScriptError(`YouTube player error${event.data ? ` (${event.data})` : ''}`);
            },
          },
        });
      })
      .catch((error: unknown) => {
        if (active) setScriptError(error instanceof Error ? error.message : 'Player unavailable');
      });
    return () => {
      active = false;
      try {
        playerRef.current?.destroy?.();
      } catch {
        // Suppress errors on cleanup
      }
      playerRef.current = null;
    };
  }, [attempt, videoId]);

  useEffect(() => {
    const changed = previousStartRef.current !== start;
    previousStartRef.current = start;
    if (start || changed) pendingSeekRef.current = { seconds: start, play: false };
    if (ready && pendingRangeRef.current) {
      playerRef.current?.loadVideoById?.({ videoId, ...pendingRangeRef.current });
      pendingRangeRef.current = null;
      pendingSeekRef.current = null;
    } else if (ready && pendingSeekRef.current) {
      const pendingSeek = pendingSeekRef.current;
      seek(pendingSeek.seconds, pendingSeek.play);
    }
  }, [ready, seek, start, videoId]);

  useImperativeHandle(ref, () => ({
    previewRange(startSeconds: number, endSeconds: number) {
      if (
        !Number.isFinite(startSeconds) ||
        !Number.isFinite(endSeconds) ||
        startSeconds < 0 ||
        endSeconds <= startSeconds
      )
        return;
      pendingSeekRef.current = null;
      pendingRangeRef.current = { startSeconds, endSeconds };
      if (ready && playerRef.current?.loadVideoById) {
        playerRef.current.loadVideoById({ videoId, startSeconds, endSeconds });
        pendingRangeRef.current = null;
      }
    },
    seekTo(seconds: number, options?: { play?: boolean }) {
      seek(seconds, options?.play ?? false);
    },
    play() {
      try {
        playerRef.current?.playVideo?.();
      } catch {
        // Suppress player API errors
      }
    },
    pause() {
      pendingRangeRef.current = null;
      if (pendingSeekRef.current) pendingSeekRef.current.play = false;
      try {
        playerRef.current?.pauseVideo?.();
      } catch {
        // Suppress player API errors
      }
    },
    togglePlay() {
      try {
        if (playerRef.current?.getPlayerState?.() === YOUTUBE_PLAYING_STATE) {
          playerRef.current.pauseVideo?.();
        } else {
          playerRef.current?.playVideo?.();
        }
      } catch {
        // Suppress player API errors
      }
    },
    getCurrentTime() {
      try {
        return playerRef.current?.getCurrentTime?.() ?? null;
      } catch {
        return null;
      }
    },
  }));

  return (
    <div className="relative aspect-video w-full overflow-hidden bg-black">
      <div ref={containerRef} title={title ?? 'YouTube player'} className="h-full w-full" />
      {!ready && !scriptError && (
        <div
          className="absolute inset-0 grid place-items-center bg-black/70 text-white"
          role="status"
        >
          Loading player…
        </div>
      )}
      {scriptError && (
        <div
          className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/90 p-6 text-center text-white"
          role="alert"
        >
          <strong>Source player unavailable</strong>
          <span className="text-sm text-white/75">{scriptError}</span>
          <div className="flex flex-wrap justify-center gap-2">
            <button
              type="button"
              className="min-h-11 rounded-lg bg-white px-4 font-semibold text-black"
              onClick={() => setAttempt((value) => value + 1)}
            >
              Retry
            </button>
            <a
              className="inline-flex min-h-11 items-center rounded-lg border border-white/50 px-4 font-semibold text-white"
              href={`https://www.youtube.com/watch?v=${videoId}&t=${Math.max(0, Math.floor(start))}s`}
              target="_blank"
              rel="noreferrer"
            >
              Open on YouTube
            </a>
          </div>
        </div>
      )}
    </div>
  );
});
