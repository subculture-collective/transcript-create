import type { SearchHit, Segment, TranscriptBlock } from '../../types/api';
import { formatTimestamp } from '../../features/archive/format';

type Props = {
  blocks: TranscriptBlock[];
  transcriptSegments: Segment[];
  hits: SearchHit[] | null;
  activeBlockIndex: number | null;
  activeSegId: number | null;
  isSavedSegment: (segment: Segment, segIndex: number) => boolean;
  onClickSentence: (segment: Segment, segIndex: number) => void;
  onSaveMoment: (segment: Segment, segIndex: number, text: string) => void;
  onCopyQuote: (segment: Segment, text: string, segIndex: number) => void;
};

type SentencePiece = {
  id: string;
  text: string;
  startMs: number;
  endMs: number;
  segmentIds: number[];
  firstSegment: Segment;
  firstSegIndex: number;
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

function normalizeSentenceText(text: string) {
  return text.replace(/\s+/g, ' ').replace(/\s+([,.!?;:])/g, '$1').trim();
}

function endsSentence(text: string) {
  return /[.!?][”"')\]]*$/.test(text.trim());
}

function buildSentencePieces(block: TranscriptBlock, transcriptSegments: Segment[]): SentencePiece[] {
  const pieces: SentencePiece[] = [];
  let currentText: string[] = [];
  let currentIds: number[] = [];

  function flush() {
    if (currentIds.length === 0) return;
    const firstId = currentIds[0];
    const lastId = currentIds[currentIds.length - 1];
    const firstSegment = transcriptSegments[firstId];
    const lastSegment = transcriptSegments[lastId] ?? firstSegment;
    const text = normalizeSentenceText(currentText.join(' '));
    if (firstSegment && text) {
      pieces.push({
        id: `${block.block_index}-${firstId}-${lastId}`,
        text,
        startMs: firstSegment.start_ms,
        endMs: lastSegment.end_ms,
        segmentIds: [...currentIds],
        firstSegment,
        firstSegIndex: firstId + 1,
      });
    }
    currentText = [];
    currentIds = [];
  }

  for (const segId of block.segment_ids) {
    const segment = transcriptSegments[segId];
    if (!segment) continue;
    const text = normalizeSentenceText(segment.text);
    if (!text) continue;
    currentText.push(text);
    currentIds.push(segId);
    if (endsSentence(text)) flush();
  }

  flush();
  return pieces.length > 0
    ? pieces
    : [{
        id: `${block.block_index}-fallback`,
        text: normalizeSentenceText(block.text),
        startMs: block.start_ms,
        endMs: block.end_ms,
        segmentIds: block.segment_ids,
        firstSegment: { start_ms: block.start_ms, end_ms: block.end_ms, text: block.text, speaker_label: block.speaker_label },
        firstSegIndex: (block.segment_ids[0] ?? 0) + 1,
      }];
}

export default function FormattedTranscriptDocument({
  blocks,
  transcriptSegments,
  hits,
  activeBlockIndex,
  activeSegId,
  isSavedSegment,
  onClickSentence,
  onSaveMoment,
  onCopyQuote,
}: Props) {
  return (
    <article className="surface-card space-y-3" role="list" aria-label="Formatted transcript document">
      {blocks.map((block) => {
        const pieces = buildSentencePieces(block, transcriptSegments);
        const selectedPiece = pieces.find((piece) => piece.segmentIds.some((segIdx) => activeSegId === segIdx + 1));
        const selectedSaved = selectedPiece
          ? selectedPiece.segmentIds.some((segIdx) => {
              const segment = transcriptSegments[segIdx];
              return segment ? isSavedSegment(segment, segIdx + 1) : false;
            })
          : false;
        const isActiveBlock = activeBlockIndex === block.block_index || Boolean(selectedPiece);

        return (
          <section
            key={block.block_index}
            id={`block-${block.block_index}`}
            className="rounded-xl px-1 py-0.5"
            role="listitem"
            data-active={isActiveBlock ? 'true' : undefined}
          >
            {block.speaker_label && (
              <div className="mb-1 text-sm font-semibold uppercase tracking-wide text-subtle">{block.speaker_label}</div>
            )}
            <div className="space-y-1.5 text-lg leading-7 text-ink">
              <p className="font-serif text-[1.05rem] leading-7">
                {pieces.map((piece) => {
                  const pieceActive = piece.segmentIds.some((segIdx) => activeSegId === segIdx + 1);
                  const pieceSaved = piece.segmentIds.some((segIdx) => {
                    const segment = transcriptSegments[segIdx];
                    return segment ? isSavedSegment(segment, segIdx + 1) : false;
                  });
                  const pieceHighlighted = piece.segmentIds.some((segIdx) =>
                    hits?.some((h) => h.start_ms >= transcriptSegments[segIdx]?.start_ms && h.start_ms < transcriptSegments[segIdx]?.end_ms)
                  );

                  return (
                    <span key={piece.id}>
                      <button
                        id={`seg-${piece.firstSegIndex}`}
                        type="button"
                        onClick={() => onClickSentence(piece.firstSegment, piece.firstSegIndex)}
                        className={`inline cursor-pointer rounded-sm bg-transparent p-0 text-left font-inherit leading-inherit text-inherit transition-colors hover:text-accent focus:bg-surface-muted focus:outline-none ${
                          pieceActive ? 'bg-accent-soft px-1 ring-1 ring-accent' : ''
                        } ${pieceHighlighted && !pieceActive ? 'bg-warning-soft px-1 ring-1 ring-warning' : ''} ${pieceSaved ? 'decoration-warning underline decoration-2 underline-offset-4' : ''}`}
                        aria-label={`Play sentence from ${msToHms(piece.startMs)}`}
                      >
                        {piece.text}
                      </button>{' '}
                    </span>
                  );
                })}
              </p>
              {selectedPiece && (
                <div className="flex flex-wrap items-center gap-3 border-l-2 border-accent pl-3 text-sm">
                  <span className="text-xs uppercase tracking-wide text-subtle">Selected {formatTimestamp(selectedPiece.startMs)}</span>
                  <button
                    type="button"
                    className="nav-link"
                    disabled={selectedSaved}
                    onClick={() => onSaveMoment({ start_ms: selectedPiece.startMs, end_ms: selectedPiece.endMs, text: selectedPiece.text, speaker_label: block.speaker_label }, selectedPiece.firstSegIndex, selectedPiece.text)}
                  >
                    {selectedSaved ? 'Saved moment' : 'Save moment'}
                  </button>
                  <button
                    type="button"
                    className="nav-link"
                    onClick={() => onCopyQuote({ start_ms: selectedPiece.startMs, end_ms: selectedPiece.endMs, text: selectedPiece.text, speaker_label: block.speaker_label }, selectedPiece.text, selectedPiece.firstSegIndex)}
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
