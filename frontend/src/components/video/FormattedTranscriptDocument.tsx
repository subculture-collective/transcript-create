import type { SearchHit, Segment, TranscriptBlock } from '../../types/api';
import { formatTimestamp } from '../../features/archive/format';

type Props = {
  blocks: TranscriptBlock[];
  transcriptSegments: Segment[];
  hits: SearchHit[] | null;
  activeBlockIndex: number | null;
  activeSegId: number | null;
  activeSentenceId: string | null;
  currentMs: number | null;
  isSavedSegment: (segment: Segment, segIndex: number) => boolean;
  onClickSentence: (segment: Segment, segIndex: number, sentenceId: string) => void;
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
  const hh = Math.floor(total / 3600).toString().padStart(2, '0');
  const mm = Math.floor((total % 3600) / 60).toString().padStart(2, '0');
  const ss = (total % 60).toString().padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

function normalizeSentenceText(text: string) {
  return text.replace(/\s+/g, ' ').replace(/\s+([,.!?;:])/g, '$1').trim();
}

function endsSentence(text: string) {
  return /[.!?][”"')\]]*$/.test(text.trim());
}

function splitIntoSentences(text: string) {
  const normalized = normalizeSentenceText(text);
  if (!normalized) return [];
  return normalized.match(/[^.!?]+[.!?]+[”"')\]]*|[^.!?]+$/g)?.map((part) => part.trim()).filter(Boolean) ?? [normalized];
}

function estimateSentenceTiming(segment: Segment, sentences: string[], sentenceIndex: number) {
  if (sentences.length <= 1) return { startMs: segment.start_ms, endMs: segment.end_ms };
  const duration = Math.max(segment.end_ms - segment.start_ms, sentences.length);
  const weights = sentences.map((sentence) => Math.max(sentence.length, 1));
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
  const startWeight = weights.slice(0, sentenceIndex).reduce((sum, weight) => sum + weight, 0);
  const endWeight = startWeight + weights[sentenceIndex];
  return {
    startMs: Math.round(segment.start_ms + (duration * startWeight) / totalWeight),
    endMs: Math.round(segment.start_ms + (duration * endWeight) / totalWeight),
  };
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
        firstSegment: { ...firstSegment, end_ms: lastSegment.end_ms, text },
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

    const segmentSentences = splitIntoSentences(text);
    if (segmentSentences.length > 1) {
      flush();
      segmentSentences.forEach((sentence, sentenceIndex) => {
        const timing = estimateSentenceTiming(segment, segmentSentences, sentenceIndex);
        pieces.push({
          id: `${block.block_index}-${segId}-s-${sentenceIndex}`,
          text: sentence,
          startMs: timing.startMs,
          endMs: timing.endMs,
          segmentIds: [segId],
          firstSegment: { ...segment, start_ms: timing.startMs, end_ms: timing.endMs, text: sentence },
          firstSegIndex: segId + 1,
        });
      });
      continue;
    }

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

function sentenceDomId(piece: SentencePiece) {
  const suffix = piece.id.includes('-s-') ? piece.id.split('-s-').at(1) : piece.id.replace(/[^a-zA-Z0-9_-]/g, '_');
  return `seg-${piece.firstSegIndex}-s-${suffix ?? 0}`;
}

export default function FormattedTranscriptDocument({
  blocks,
  transcriptSegments,
  hits,
  activeBlockIndex,
  activeSegId,
  activeSentenceId,
  currentMs,
  isSavedSegment,
  onClickSentence,
  onSaveMoment,
  onCopyQuote,
}: Props) {
  return (
    <article className="surface-card space-y-5" aria-label="Readable transcript">
      {blocks.map((block) => {
        const pieces = buildSentencePieces(block, transcriptSegments);
        const selectedPiece = pieces.find((piece) => activeSentenceId === piece.id) ?? pieces.find((piece) => piece.segmentIds.some((segIdx) => activeSegId === segIdx + 1));
        const selectedSaved = selectedPiece ? isSavedSegment(selectedPiece.firstSegment, selectedPiece.firstSegIndex) : false;
        const isActiveBlock = activeBlockIndex === block.block_index || Boolean(selectedPiece);

        return (
          <section key={block.block_index} id={`block-${block.block_index}`} className="rounded-xl px-1 py-0.5" data-active={isActiveBlock ? 'true' : undefined}>
            {block.speaker_label && <div className="mb-1 text-sm font-semibold uppercase tracking-wide text-subtle">{block.speaker_label}</div>}
            <p className="font-serif text-[1.05rem] leading-8 text-ink">
              {pieces.map((piece) => {
                const pieceActive = activeSentenceId ? activeSentenceId === piece.id : piece.segmentIds.some((segIdx) => activeSegId === segIdx + 1);
                const pieceCurrent = currentMs != null && currentMs >= piece.startMs && currentMs < piece.endMs;
                const pieceSaved = isSavedSegment(piece.firstSegment, piece.firstSegIndex);
                const pieceHighlighted = piece.segmentIds.some((segIdx) =>
                  hits?.some((h) => h.start_ms >= transcriptSegments[segIdx]?.start_ms && h.start_ms < transcriptSegments[segIdx]?.end_ms)
                );

                return (
                  <span key={piece.id}>
                    <span
                      id={sentenceDomId(piece)}
                      role="button"
                      tabIndex={0}
                      data-current-sentence={pieceCurrent ? 'true' : undefined}
                      onClick={() => onClickSentence(piece.firstSegment, piece.firstSegIndex, piece.id)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          onClickSentence(piece.firstSegment, piece.firstSegIndex, piece.id);
                        }
                      }}
                      className={`cursor-pointer rounded-sm decoration-warning decoration-2 underline-offset-4 transition-colors hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/50 ${
                        pieceActive ? 'bg-accent-soft px-1 text-accent ring-1 ring-accent/70' : ''
                      } ${pieceCurrent && !pieceActive ? 'text-accent' : ''} ${pieceHighlighted && !pieceActive ? 'bg-warning-soft px-1 text-warning' : ''} ${pieceSaved ? 'underline' : ''}`}
                      aria-label={`Play sentence from ${msToHms(piece.startMs)}`}
                    >
                      {piece.text}
                    </span>{' '}
                  </span>
                );
              })}
            </p>
            {selectedPiece && (
              <div className="mt-2 flex flex-wrap items-center gap-3 border-l-2 border-accent pl-3 text-sm">
                <span className="text-xs uppercase tracking-wide text-subtle">Selected {formatTimestamp(selectedPiece.startMs)}</span>
                <button type="button" className="nav-link" disabled={selectedSaved} onClick={() => onSaveMoment(selectedPiece.firstSegment, selectedPiece.firstSegIndex, selectedPiece.text)}>
                  {selectedSaved ? 'Saved moment' : 'Save moment'}
                </button>
                <button type="button" className="nav-link" onClick={() => onCopyQuote(selectedPiece.firstSegment, selectedPiece.text, selectedPiece.firstSegIndex)}>
                  Copy quote
                </button>
              </div>
            )}
          </section>
        );
      })}
    </article>
  );
}
