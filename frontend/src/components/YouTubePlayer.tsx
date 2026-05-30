import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from 'react';

type YouTubePlayer = {
  destroy?: () => void;
  seekTo?: (seconds: number, allowSeekAhead: boolean) => void;
  playVideo?: () => void;
  getPlayerState?: () => number;
};

type YouTubePlayerConstructor = {
  new (element: HTMLElement, config: {
    height: string;
    width: string;
    videoId: string;
    playerVars: { start: number; autoplay: number };
    events: { onReady: () => void };
  }): YouTubePlayer;
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
};

type Props = { videoId: string; start?: number; title?: string };

const YOUTUBE_PLAYING_STATE = 1;

export default forwardRef<YouTubePlayerHandle, Props>(function YouTubePlayer(
  { videoId, start = 0, title },
  ref
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<YouTubePlayer | null>(null);
  const pendingSeekRef = useRef<{ seconds: number; play: boolean } | null>(null);
  const [ready, setReady] = useState(false);

  function seek(seconds: number, play = false) {
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
  }

  useEffect(() => {
    function loadApi() {
      if (window.YT && window.YT.Player) return Promise.resolve();
      return new Promise<void>((resolve) => {
        const tag = document.createElement('script');
        tag.src = 'https://www.youtube.com/iframe_api';
        document.body.appendChild(tag);
        window.onYouTubeIframeAPIReady = () => resolve();
      });
    }
    loadApi().then(() => {
      if (!containerRef.current || !window.YT?.Player) return;
      playerRef.current = new window.YT.Player(containerRef.current, {
        height: '100%',
        width: '100%',
        videoId,
        playerVars: { start, autoplay: 0 },
        events: {
          onReady: () => setReady(true),
        },
      });
    });
    return () => {
      try {
        playerRef.current?.destroy?.();
      } catch {
        // Suppress errors on cleanup
      }
    };
  }, [videoId]);

  useEffect(() => {
    if (ready) {
      const pending = pendingSeekRef.current;
      if (pending) seek(pending.seconds, pending.play);
      else if (start) seek(start, false);
    }
  }, [ready, start]);

  useImperativeHandle(ref, () => ({
    seekTo(seconds: number, options?: { play?: boolean }) {
      seek(seconds, options?.play ?? false);
    },
  }));

  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg border bg-black">
      <div ref={containerRef} title={title ?? 'YouTube player'} className="h-full w-full" />
    </div>
  );
});
