import type { SearchHit, Segment, TranscriptBlock } from '../../types/api';
import { formatTimestamp } from '../../features/archive/format';

type Props = {
  blocks: TranscriptBlock[];
  transcriptSegments: Segment[];
  hits: SearchHit[] | null;
  activeBlockIndex: number | null;
  activeSegId: number | null;
  isSavedBlock: (block: TranscriptBlock) => boolean;
  onClickBlock: (block: TranscriptBlock) => void;
  onSaveMoment: (segment: Segment, segIndex: number, text: string) => void;
  onCopyQuote: (segment: Segment, text: string, segIndex: number) => void;
};

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

export default function FormattedTranscriptDocument({
  blocks,
  transcriptSegments,
  hits,
  activeBlockIndex,
  activeSegId,
  isSavedBlock,
  onClickBlock,
  onSaveMoment,
  onCopyQuote,
}: Props) {
  return (
    <article className="surface-card space-y-7" role="list" aria-label="Formatted transcript document">
      {blocks.map((block) => {
        const saved = isSavedBlock(block);
        const isHighlighted = block.segment_ids.some((segIdx) =>
          hits?.some((h) => h.start_ms >= transcriptSegments[segIdx]?.start_ms && h.start_ms < transcriptSegments[segIdx]?.end_ms)
        );
        const isActive = activeBlockIndex === block.block_index || block.segment_ids.some((segIdx) => activeSegId === segIdx + 1);

        return (
          <section
            key={block.block_index}
            id={`block-${block.block_index}`}
            className={`rounded-xl px-1 py-1 transition-colors ${isActive ? 'bg-accent-soft/60 ring-1 ring-accent' : ''}`}
            role="listitem"
          >
            {block.speaker_label && (
              <div className="mb-2 text-sm font-semibold uppercase tracking-wide text-subtle">{block.speaker_label}</div>
            )}
            <div className="space-y-3 text-lg leading-8 text-ink">
              <button
                type="button"
                onClick={() => onClickBlock(block)}
                className={`w-full cursor-pointer rounded-lg px-3 py-2 text-left font-serif text-[1.05rem] leading-8 transition-colors hover:bg-surface-muted focus:bg-surface-muted ${
                  isHighlighted && !isActive ? 'bg-warning-soft ring-1 ring-warning' : ''
                } ${saved ? 'decoration-warning underline decoration-2 underline-offset-4' : ''}`}
                aria-label={`Play ${block.speaker_label ?? 'paragraph'} from ${msToHms(block.start_ms)}`}
              >
                {block.text}
              </button>
              {isActive && (
                <div className="flex flex-wrap items-center gap-3 border-l-2 border-accent pl-3 text-sm">
                  <span className="text-xs uppercase tracking-wide text-subtle">Selected {formatTimestamp(block.start_ms)}</span>
                  <button
                    type="button"
                    className="nav-link"
                    disabled={saved}
                    onClick={() => onSaveMoment({ start_ms: block.start_ms, end_ms: block.end_ms, text: block.text, speaker_label: block.speaker_label }, (block.segment_ids[0] ?? 0) + 1, block.text)}
                  >
                    {saved ? 'Saved moment' : 'Save moment'}
                  </button>
                  <button
                    type="button"
                    className="nav-link"
                    onClick={() => onCopyQuote({ start_ms: block.start_ms, end_ms: block.end_ms, text: block.text, speaker_label: block.speaker_label }, block.text, (block.segment_ids[0] ?? 0) + 1)}
                  >
                    Copy quote
                  </button>
                </div>
              )}
            </div>
          </section>
        );
      })}
    </article>
  );
}
