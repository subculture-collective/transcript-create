import { useEffect, useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
import type { VideoChapter } from '../../types/api';
import type { YouTubePlayerHandle } from '../YouTubePlayer';
import EpisodeOutline from './EpisodeOutline';

type Props = {
  chapters: VideoChapter[];
  onSelectChapter: (chapter: VideoChapter) => void;
  playerRef: RefObject<YouTubePlayerHandle | null>;
  transcriptKey: string;
  autoFollow: boolean;
  onAutoScroll: (element: HTMLElement) => void;
  onPlaybackTime?: (currentMs: number) => void;
  /** Renders playback-aware UI; defaults to the chapter outline. */
  children?: (currentMs: number | null) => ReactNode;
};

const TICK_MS = 250;

function sentenceElements() {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-transcript-sentence="true"]'));
}

/**
 * Keeps the transcript in step with the player without re-rendering it: the
 * current sentence gets a class and a sweep percentage, earlier sentences are
 * marked as played, and the document is flagged once playback has a position.
 */
export default function PlaybackProgress({
  chapters,
  onSelectChapter,
  playerRef,
  transcriptKey,
  autoFollow,
  onAutoScroll,
  onPlaybackTime,
  children,
}: Props) {
  const [currentMs, setCurrentMs] = useState<number | null>(null);
  const currentElementRef = useRef<HTMLElement | null>(null);
  const lastScrollAtRef = useRef(0);
  const lastReportedSecondRef = useRef<number | null>(null);
  // Callbacks change identity on every parent render; read the latest through refs
  // so the sync loop is rebuilt only when the transcript or follow mode changes.
  const onPlaybackTimeRef = useRef(onPlaybackTime);
  const onAutoScrollRef = useRef(onAutoScroll);
  useEffect(() => {
    onPlaybackTimeRef.current = onPlaybackTime;
    onAutoScrollRef.current = onAutoScroll;
  });

  useEffect(() => {
    const elements = sentenceElements();
    const starts = elements.map((element) => Number(element.dataset.startMs ?? 0));
    let playedThrough = -1;
    let progressFlagged = false;

    const markPlayed = (index: number) => {
      // Only the range between the old and new position changes.
      if (index > playedThrough) {
        for (let i = Math.max(playedThrough, 0); i < index; i += 1)
          elements[i]?.setAttribute('data-played', 'true');
      } else if (index < playedThrough) {
        for (let i = Math.max(index, 0); i < playedThrough; i += 1)
          elements[i]?.removeAttribute('data-played');
      }
      elements[index]?.removeAttribute('data-played');
      playedThrough = index;
    };

    const tick = () => {
      const seconds = playerRef.current?.getCurrentTime();
      if (seconds == null || !Number.isFinite(seconds)) return;
      const nextMs = Math.floor(seconds * 1000);
      const wholeSecond = Math.floor(nextMs / 1000);
      if (wholeSecond !== lastReportedSecondRef.current) {
        lastReportedSecondRef.current = wholeSecond;
        setCurrentMs(nextMs);
        onPlaybackTimeRef.current?.(nextMs);
      }

      let low = 0;
      let high = starts.length - 1;
      let candidate = -1;
      while (low <= high) {
        const middle = (low + high) >> 1;
        if (starts[middle] <= nextMs) {
          candidate = middle;
          low = middle + 1;
        } else {
          high = middle - 1;
        }
      }

      if (nextMs > 0 && !progressFlagged) {
        progressFlagged = true;
        for (const doc of document.querySelectorAll('.transcript-document'))
          doc.setAttribute('data-progress', 'on');
      }
      markPlayed(candidate);

      const nextElement = candidate >= 0 ? elements[candidate] : null;
      const endMs = Number(nextElement?.dataset.endMs ?? 0);
      const activeElement = nextElement && nextMs < endMs ? nextElement : null;
      if (activeElement) {
        const startMs = starts[candidate];
        const span = Math.max(endMs - startMs, 1);
        const sweep = Math.min(100, Math.max(0, ((nextMs - startMs) / span) * 100));
        activeElement.style.setProperty('--sweep', `${sweep.toFixed(1)}%`);
      }
      if (activeElement === currentElementRef.current) return;

      const previous = currentElementRef.current;
      previous?.classList.remove('transcript-sentence-current');
      previous?.removeAttribute('data-current-sentence');
      previous?.style.removeProperty('--sweep');
      previous?.closest('.transcript-paragraph, .transcript-block')?.removeAttribute('data-now');
      currentElementRef.current = activeElement;
      activeElement?.classList.add('transcript-sentence-current');
      activeElement?.setAttribute('data-current-sentence', 'true');
      activeElement
        ?.closest('.transcript-paragraph, .transcript-block')
        ?.setAttribute('data-now', 'true');

      const now = Date.now();
      if (autoFollow && activeElement && now - lastScrollAtRef.current >= 1500) {
        onAutoScrollRef.current(activeElement);
        lastScrollAtRef.current = now;
      }
    };

    const interval = window.setInterval(tick, TICK_MS);

    return () => {
      window.clearInterval(interval);
      const current = currentElementRef.current;
      current?.classList.remove('transcript-sentence-current');
      current?.removeAttribute('data-current-sentence');
      current?.style.removeProperty('--sweep');
      current?.closest('.transcript-paragraph, .transcript-block')?.removeAttribute('data-now');
      currentElementRef.current = null;
      for (const element of elements) element.removeAttribute('data-played');
      lastReportedSecondRef.current = null;
    };
  }, [autoFollow, playerRef, transcriptKey]);

  if (children) return <>{children(currentMs)}</>;
  return <EpisodeOutline chapters={chapters} currentMs={currentMs} onSelect={onSelectChapter} />;
}
