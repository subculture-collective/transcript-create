import { act, render } from '@testing-library/react';
import { createRef } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PlaybackProgress from '../components/video/PlaybackProgress';
import type { YouTubePlayerHandle } from '../components/YouTubePlayer';

describe('PlaybackProgress', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('updates only the previous and next active transcript nodes', () => {
    let seconds = 0.5;
    const playerRef = createRef<YouTubePlayerHandle>();
    playerRef.current = { getCurrentTime: () => seconds } as YouTubePlayerHandle;
    const { container } = render(
      <div>
        <button data-transcript-sentence="true" data-start-ms="0" data-end-ms="1000">
          First
        </button>
        <button data-transcript-sentence="true" data-start-ms="1000" data-end-ms="2000">
          Second
        </button>
        <PlaybackProgress
          chapters={[]}
          onSelectChapter={vi.fn()}
          playerRef={playerRef}
          transcriptKey="video:2"
          autoFollow={false}
          onAutoScroll={vi.fn()}
        />
      </div>
    );
    const [first, second] = Array.from(
      container.querySelectorAll<HTMLElement>('[data-transcript-sentence="true"]')
    );

    act(() => vi.advanceTimersByTime(750));
    expect(first).toHaveClass('transcript-sentence-current');
    expect(second).not.toHaveClass('transcript-sentence-current');

    seconds = 1.5;
    act(() => vi.advanceTimersByTime(750));
    expect(first).not.toHaveClass('transcript-sentence-current');
    expect(second).toHaveClass('transcript-sentence-current');
  });

  it('marks spoken text, sweeps the current sentence, and reports playback time', () => {
    let seconds = 0.5;
    const playerRef = createRef<YouTubePlayerHandle>();
    playerRef.current = { getCurrentTime: () => seconds } as YouTubePlayerHandle;
    const onPlaybackTime = vi.fn();
    const { container } = render(
      <div>
        <article className="transcript-document">
          {[0, 1000, 2000].map((start) => (
            <span
              key={start}
              data-transcript-sentence="true"
              data-start-ms={start}
              data-end-ms={start + 1000}
            >
              Sentence
            </span>
          ))}
        </article>
        <PlaybackProgress
          chapters={[]}
          onSelectChapter={vi.fn()}
          playerRef={playerRef}
          transcriptKey="video:3"
          autoFollow={false}
          onAutoScroll={vi.fn()}
          onPlaybackTime={onPlaybackTime}
        >
          {(currentMs) => <output>{currentMs ?? 'idle'}</output>}
        </PlaybackProgress>
      </div>
    );
    const sentences = Array.from(
      container.querySelectorAll<HTMLElement>('[data-transcript-sentence="true"]')
    );
    expect(container.querySelector('output')).toHaveTextContent('idle');

    seconds = 2.25;
    act(() => vi.advanceTimersByTime(250));
    expect(container.querySelector('.transcript-document')).toHaveAttribute('data-progress', 'on');
    expect(sentences.map((sentence) => sentence.getAttribute('data-played'))).toEqual([
      'true',
      'true',
      null,
    ]);
    expect(sentences[2]).toHaveClass('transcript-sentence-current');
    expect(sentences[2].style.getPropertyValue('--sweep')).toBe('25.0%');
    expect(onPlaybackTime).toHaveBeenLastCalledWith(2250);
    expect(container.querySelector('output')).toHaveTextContent('2250');

    seconds = 0.5;
    act(() => vi.advanceTimersByTime(250));
    expect(sentences.map((sentence) => sentence.getAttribute('data-played'))).toEqual([
      null,
      null,
      null,
    ]);
    expect(sentences[0]).toHaveClass('transcript-sentence-current');
  });
});
