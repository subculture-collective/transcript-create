import type { VideoChapter } from '../../types/api';
import { formatTimestamp } from '../../features/archive/format';

type Props = {
  chapters: VideoChapter[];
  currentMs: number | null;
  onSelect: (chapter: VideoChapter) => void;
};

export default function EpisodeOutline({ chapters, currentMs, onSelect }: Props) {
  const activeIndex =
    currentMs == null
      ? -1
      : chapters.findIndex(
          (chapter) => currentMs >= chapter.start_ms && currentMs < chapter.end_ms
        );

  if (chapters.length === 0) return null;

  return (
    <details className="outline-panel" open>
      <summary className="outline-heading">
        <span>
          <span className="meta-label block">Episode outline</span>
          <span className="mt-1 block text-xs text-subtle">{chapters.length} cited chapters</span>
        </span>
        <span className="font-mono text-[10px] text-accent">Navigate ↓</span>
      </summary>
      <nav className="outline-list" aria-label="Episode chapters">
        {chapters.map((chapter, index) => {
          const active = index === activeIndex;
          const citation = chapter.evidence[0];
          return (
            <button
              key={`${chapter.chapter_index}-${chapter.start_ms}`}
              type="button"
              className={`outline-item ${active ? 'outline-item-active' : ''}`}
              onClick={() => onSelect(chapter)}
              aria-current={active ? 'location' : undefined}
            >
              <span className="outline-index">{String(index + 1).padStart(2, '0')}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-3">
                  <span className="outline-title">{chapter.title}</span>
                  <span className="outline-time">{formatTimestamp(chapter.start_ms)}</span>
                </span>
                {active && (
                  <span className="mt-2 block text-left text-xs leading-5 text-muted">
                    {chapter.summary}
                    {citation && (
                      <span className="mt-2 block border-l border-accent/40 pl-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-subtle">
                        Evidence · transcript at {formatTimestamp(citation.start_ms)}
                        {citation.text.trim() !== chapter.summary.trim() && (
                          <span className="mt-1 block font-serif text-[11px] font-normal normal-case tracking-normal italic">
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
    </details>
  );
}
