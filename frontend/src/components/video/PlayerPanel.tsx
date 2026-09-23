import type { RefObject } from 'react';
import type { VideoInfo } from '../../types/api';
import YouTubePlayer, { type YouTubePlayerHandle } from '../YouTubePlayer';

type Props = {
  video: VideoInfo | null;
  start: number;
  playerRef: RefObject<YouTubePlayerHandle | null>;
  className?: string;
};

export default function PlayerPanel({ video, start, playerRef, className = '' }: Props) {
  return (
    <div className={`overflow-hidden bg-black ${className}`}>
      {video ? (
        <YouTubePlayer
          ref={playerRef}
          videoId={video.youtube_id}
          start={start}
          title={video?.title ?? undefined}
        />
      ) : (
        <div className="aspect-video w-full overflow-hidden bg-black">
          <div
            className="flex h-full items-center justify-center text-subtle"
            role="status"
            aria-live="polite"
          >
            <span className="mr-3 inline-block animate-spin text-3xl" aria-hidden="true">
              ⟳
            </span>
            Loading player…
          </div>
        </div>
      )}
    </div>
  );
}
