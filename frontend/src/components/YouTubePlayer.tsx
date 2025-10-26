import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from 'react';

type YouTubePlayer = {
  destroy?: () => void;
  seekTo?: (seconds: number, allowSeekAhead: boolean) => void;
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
  seekTo: (seconds: number) => void;
};

type Props = { videoId: string; start?: number; title?: string };

export default forwardRef<YouTubePlayerHandle, Props>(function YouTubePlayer(
  { videoId, start = 0, title },
  ref
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<YouTubePlayer | null>(null);
  const [ready, setReady] = useState(false);

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
        height: '390',
        width: '640',
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
  }, [videoId, start]);

  useEffect(() => {
    if (ready && start) {
      try {
        playerRef.current?.seekTo?.(start, true);
      } catch {
        // Suppress errors during seek
      }
    }
  }, [ready, start]);

  useImperativeHandle(ref, () => ({
    seekTo(seconds: number) {
      try {
        playerRef.current?.seekTo?.(seconds, true);
      } catch {
        // Suppress errors during seek
      }
    },
  }));

  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg border bg-black">
      <div ref={containerRef} title={title ?? 'YouTube player'} />
    </div>
  );
});
