import { useEffect, useRef } from 'react';
import type { VideoChapter } from '../../types/api';
import { formatTimestamp } from '../../features/archive/format';

type Props = {
  chapters: VideoChapter[];
  currentMs: number | null;
  onSelect: (chapter: VideoChapter) => void;
  /** Render only the list, for use inside the episode navigator. */
  embedded?: boolean;
};

const FILLER_TITLE = /^(okay|i mean|um|uh|you know)[.!?…\s]*$/i;

// eslint-disable-next-line react-refresh/only-export-components
export function visibleOutlineChapters(chapters: VideoChapter[]) {
  return chapters.filter((chapter) => !FILLER_TITLE.test(chapter.title.trim()));
}

export default function EpisodeOutline({ chapters, currentMs, onSelect, embedded = false }: Props) {
  const visibleChapters = visibleOutlineChapters(chapters);
  const activeIndex =
    currentMs == null
      ? -1
      : visibleChapters.findIndex(
          (chapter) => currentMs >= chapter.start_ms && currentMs < chapter.end_ms
        );
  const activeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (activeIndex < 0) return;
    activeRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
  }, [activeIndex]);

  if (visibleChapters.length === 0) return null;

  const list = (
    <nav className="outline-list" aria-label="Transcript landmarks">
      {visibleChapters.map((chapter, index) => {
        const active = index === activeIndex;
        const played = currentMs != null && chapter.end_ms <= currentMs;
        const citation = chapter.evidence[0];
        const hasSummary =
          chapter.summary.trim() && chapter.summary.trim() !== chapter.title.trim();
        return (
          <button
            key={`${chapter.chapter_index}-${chapter.start_ms}`}
            ref={active ? activeRef : undefined}
            type="button"
            className={`outline-item ${active ? 'outline-item-active' : ''}`}
            data-played={played ? 'true' : undefined}
            onClick={() => onSelect(chapter)}
            aria-current={active ? 'location' : undefined}
          >
            <span className="outline-index" aria-hidden="true">
              {index + 1}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline justify-between gap-3">
                <span className="outline-title">{chapter.title}</span>
                <span className="outline-time">{formatTimestamp(chapter.start_ms)}</span>
              </span>
              {active && (
                <span className="mt-1.5 block text-left text-xs leading-5 text-muted">
                  {hasSummary && <span className="block">{chapter.summary}</span>}
                  {citation && (
                    <span className="mt-1 block text-[11px] text-subtle">
                      Evidence · transcript at {formatTimestamp(citation.start_ms)}
                      {citation.text.trim() !== chapter.summary.trim() && (
                        <span className="mt-1 block font-serif text-[13px] italic">
                          “{citation.text}”
                        </span>
                      )}
                    </span>
                  )}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </nav>
  );

  if (embedded) return list;

  return (
    <details className="outline-panel" open>
      <summary className="outline-heading">
        <span>
          <span className="meta-label block">Transcript landmarks</span>
          <span className="mt-1 block text-xs text-subtle">
            {visibleChapters.length} generated, cited sections
          </span>
        </span>
      </summary>
      {list}
    </details>
  );
}
