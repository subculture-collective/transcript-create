import type { MouseEvent } from 'react';
import type { VideoChapter } from '../../types/api';
import { formatTimestamp } from '../../features/archive/format';

export type StripTick = { ms: number; kind: 'match' | 'topic' };

type Props = {
  durationMs: number;
  chapters: VideoChapter[];
  currentMs: number | null;
  ticks: StripTick[];
  onSeek: (ms: number) => void;
};

const WIDTH = 1000;

function x(ms: number, durationMs: number) {
  return Math.min(WIDTH, Math.max(0, (ms / durationMs) * WIDTH));
}

/**
 * A scaled map of the whole episode: chapters as blocks, search or topic hits
 * as ticks, and the playhead. Positions are SVG attributes because the
 * content security policy forbids inline styles.
 */
export default function EpisodeStrip({ durationMs, chapters, currentMs, ticks, onSeek }: Props) {
  if (!durationMs || durationMs <= 0) return null;

  function seekFromPointer(event: MouseEvent<HTMLDivElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    if (box.width <= 0) return;
    const fraction = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    onSeek(Math.floor(fraction * durationMs));
  }

  const playhead = currentMs == null ? null : x(currentMs, durationMs);

  return (
    <div className="episode-strip-wrap">
      <div className="episode-strip" onClick={seekFromPointer} aria-hidden="true">
        <svg viewBox={`0 0 ${WIDTH} 36`} preserveAspectRatio="none" focusable="false">
          {chapters.map((chapter) => {
            const start = x(chapter.start_ms, durationMs);
            const end = x(chapter.end_ms, durationMs);
            const active =
              currentMs != null && currentMs >= chapter.start_ms && currentMs < chapter.end_ms;
            return (
              <rect
                key={`${chapter.chapter_index}:${chapter.start_ms}`}
                className="episode-strip-chapter"
                data-active={active ? 'true' : undefined}
                x={start + 1}
                y={4}
                width={Math.max(end - start - 2, 1)}
                height={28}
                rx={3}
              >
                <title>{`${formatTimestamp(chapter.start_ms)} · ${chapter.title}`}</title>
              </rect>
            );
          })}
          {playhead != null && (
            <rect className="episode-strip-played" x={0} y={0} width={playhead} height={36} />
          )}
          {ticks.map((tick, index) => (
            <rect
              key={`${tick.kind}:${tick.ms}:${index}`}
              className="episode-strip-tick"
              data-kind={tick.kind}
              x={x(tick.ms, durationMs) - 1}
              y={tick.kind === 'topic' ? 4 : 18}
              width={2.5}
              height={14}
              rx={1}
            />
          ))}
          {playhead != null && (
            <rect className="episode-strip-playhead" x={playhead - 1} y={0} width={2} height={36} />
          )}
        </svg>
      </div>
      <div className="mt-1.5 flex justify-between font-mono text-[11px] text-subtle">
        <span>{currentMs == null ? '00:00:00' : formatTimestamp(currentMs)}</span>
        <span>{formatTimestamp(durationMs)}</span>
      </div>
    </div>
  );
}
