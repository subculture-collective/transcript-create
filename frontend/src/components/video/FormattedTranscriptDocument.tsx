import { Fragment, memo, useMemo } from 'react';
import type { SearchHit, Segment, TranscriptBlock, VideoChapter } from '../../types/api';
import {
  canonicalMomentId,
  formatTimestamp,
  type TranscriptSource,
} from '../../features/archive/format';
import { normalizeTranscriptText } from '../../features/videoTranscript/transcript';
import SectionActions from './SectionActions';

type Props = {
  blocks: TranscriptBlock[];
  source: TranscriptSource;
  transcriptSegments: Segment[];
  hits: SearchHit[] | null;
  activeBlockIndex: number | null;
  activeSegId: number | null;
  activeSentenceId: string | null;
  chapters?: VideoChapter[];
  isSavedSegment: (segment: Segment, segIndex: number) => boolean;
  /** Opens (or closes) the passage actions for a sentence. */
  onClickSentence: (segment: Segment, segIndex: number, sentenceId: string) => void;
  onPlayFrom: (segment: Segment, segIndex: number, sentenceId: string) => void;
  onCloseSelection: () => void;
  onSaveMoment: (segment: Segment, segIndex: number, text: string) => void;
  onSharePassage?: (segment: Segment) => void;
  onCopyQuote: (segment: Segment, text: string, segIndex: number) => void;
  onCopyLink: (segment: Segment, segIndex: number) => void;
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

function endsSentence(text: string) {
  return /[.!?][”"')\]]*$/.test(text.trim());
}

function splitIntoSentences(text: string) {
  const normalized = normalizeTranscriptText(text);
  if (!normalized) return [];
  return (
    normalized
      .match(/[^.!?]+[.!?]+[”"')\]]*|[^.!?]+$/g)
      ?.map((part) => part.trim())
      .filter(Boolean) ?? [normalized]
  );
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

function buildSentencePieces(
  block: TranscriptBlock,
  transcriptSegments: Segment[]
): SentencePiece[] {
  const pieces: SentencePiece[] = [];
  let currentText: string[] = [];
  let currentIds: number[] = [];

  function flush() {
    if (currentIds.length === 0) return;
    const firstId = currentIds[0];
    const lastId = currentIds[currentIds.length - 1];
    const firstSegment = transcriptSegments[firstId];
    const lastSegment = transcriptSegments[lastId] ?? firstSegment;
    const text = normalizeTranscriptText(currentText.join(' '));
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
    const text = normalizeTranscriptText(segment.text);
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
          firstSegment: {
            ...segment,
            start_ms: timing.startMs,
            end_ms: timing.endMs,
            text: sentence,
          },
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
    : [
        {
          id: `${block.block_index}-fallback`,
          text: normalizeTranscriptText(block.text),
          startMs: block.start_ms,
          endMs: block.end_ms,
          segmentIds: block.segment_ids,
          firstSegment: {
            start_ms: block.start_ms,
            end_ms: block.end_ms,
            text: block.text,
            speaker_label: block.speaker_label,
          },
          firstSegIndex: (block.segment_ids[0] ?? 0) + 1,
        },
      ];
}

/** Break long formatted blocks into readable paragraphs at sentence ends. */
const PARAGRAPH_WORDS = 80;
function splitIntoParagraphs(pieces: SentencePiece[]) {
  const paragraphs: SentencePiece[][] = [];
  let current: SentencePiece[] = [];
  let words = 0;
  for (const piece of pieces) {
    current.push(piece);
    words += piece.text.split(/\s+/).length;
    if (words >= PARAGRAPH_WORDS && endsSentence(piece.text)) {
      paragraphs.push(current);
      current = [];
      words = 0;
    }
  }
  if (current.length) {
    // Fold a short tail into the previous paragraph rather than leave a stub.
    if (paragraphs.length && words < PARAGRAPH_WORDS / 3) paragraphs.at(-1)!.push(...current);
    else paragraphs.push(current);
  }
  return paragraphs;
}

function sentenceDomId(piece: SentencePiece) {
  const suffix = piece.id.includes('-s-')
    ? piece.id.split('-s-').at(1)
    : piece.id.replace(/[^a-zA-Z0-9_-]/g, '_');
  return `seg-${piece.firstSegIndex}-s-${suffix ?? 0}`;
}

function FormattedTranscriptDocument({
  source,
  blocks,
  transcriptSegments,
  hits,
  activeBlockIndex,
  activeSegId,
  activeSentenceId,
  chapters = [],
  isSavedSegment,
  onClickSentence,
  onPlayFrom,
  onCloseSelection,
  onSaveMoment,
  onCopyQuote,
  onCopyLink,
  onSharePassage,
}: Props) {
  const preparedBlocks = useMemo(
    () =>
      blocks.map((block) => ({ block, pieces: buildSentencePieces(block, transcriptSegments) })),
    [blocks, transcriptSegments]
  );
  const hitSegmentIds = useMemo(() => {
    const ids = new Set<number>();
    for (const hit of hits ?? []) {
      let low = 0;
      let high = transcriptSegments.length - 1;
      while (low <= high) {
        const middle = (low + high) >> 1;
        const segment = transcriptSegments[middle];
        if (hit.start_ms < segment.start_ms) high = middle - 1;
        else if (hit.start_ms >= segment.end_ms) low = middle + 1;
        else {
          ids.add(middle);
          break;
        }
      }
    }
    return ids;
  }, [hits, transcriptSegments]);
  // Each chapter heading sits before the first mounted block that reaches it.
  const headingsByBlock = useMemo(() => {
    const byBlock = new Map<number, VideoChapter[]>();
    let cursor = 0;
    const ordered = [...chapters].sort((left, right) => left.start_ms - right.start_ms);
    for (const chapter of ordered) {
      while (cursor < blocks.length && blocks[cursor].end_ms <= chapter.start_ms) cursor += 1;
      const block = blocks[cursor];
      if (!block || chapter.end_ms <= block.start_ms) continue;
      const list = byBlock.get(block.block_index) ?? [];
      list.push(chapter);
      byBlock.set(block.block_index, list);
    }
    return byBlock;
  }, [blocks, chapters]);
  return (
    <article className="transcript-document" aria-label="Readable transcript">
      {preparedBlocks.map(({ block, pieces }) => {
        const headings = headingsByBlock.get(block.block_index) ?? [];
        const selectedPiece =
          pieces.find((piece) => activeSentenceId === piece.id) ??
          pieces.find((piece) => piece.segmentIds.some((segIdx) => activeSegId === segIdx + 1));
        const selectedSaved = selectedPiece
          ? isSavedSegment(selectedPiece.firstSegment, selectedPiece.firstSegIndex)
          : false;
        const isActiveBlock = activeBlockIndex === block.block_index || Boolean(selectedPiece);

        return (
          <Fragment key={block.block_index}>
            {headings.map((chapter) => (
              <div
                key={`chapter:${chapter.chapter_index}:${chapter.start_ms}`}
                id={`chapter-${chapter.chapter_index}`}
                className="transcript-chapter-heading"
              >
                <span className="font-mono text-xs text-accent">
                  {formatTimestamp(chapter.start_ms)}
                </span>
                <h3>{chapter.title}</h3>
              </div>
            ))}
            <section
              id={`block-${block.block_index}`}
              className="transcript-block content-auto"
              data-active={isActiveBlock ? 'true' : undefined}
            >
              {splitIntoParagraphs(pieces).map((paragraph, paragraphIndex) => {
                const first = paragraph[0];
                const open = Boolean(selectedPiece && paragraph.includes(selectedPiece));
                return (
                  <div
                    key={first.id}
                    className="transcript-paragraph"
                    data-open={open ? 'true' : undefined}
                  >
                    <div className="transcript-block-meta">
                      <button
                        type="button"
                        className="transcript-timecode"
                        onClick={() =>
                          onPlayFrom(first.firstSegment, first.firstSegIndex, first.id)
                        }
                        aria-label={`Play from ${formatTimestamp(first.startMs)}`}
                      >
                        {formatTimestamp(first.startMs)}
                      </button>
                      {paragraphIndex === 0 && block.speaker_label && (
                        <div className="transcript-speaker">{block.speaker_label}</div>
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="transcript-copy">
                        {paragraph.map((piece) => {
                          const pieceActive = activeSentenceId
                            ? activeSentenceId === piece.id
                            : piece.segmentIds.some((segIdx) => activeSegId === segIdx + 1);
                          const pieceSaved = isSavedSegment(
                            piece.firstSegment,
                            piece.firstSegIndex
                          );
                          const pieceHighlighted = piece.segmentIds.some((segIdx) =>
                            hitSegmentIds.has(segIdx)
                          );

                          return (
                            <span key={piece.id} id={canonicalMomentId(source, piece.startMs)}>
                              <span
                                id={sentenceDomId(piece)}
                                role="button"
                                aria-expanded={pieceActive}
                                data-transcript-sentence="true"
                                data-start-ms={piece.startMs}
                                data-end-ms={piece.endMs}
                                tabIndex={0}
                                onClick={() =>
                                  onClickSentence(piece.firstSegment, piece.firstSegIndex, piece.id)
                                }
                                onKeyDown={(event) => {
                                  if (event.key === 'Enter' || event.key === ' ') {
                                    event.preventDefault();
                                    onClickSentence(
                                      piece.firstSegment,
                                      piece.firstSegIndex,
                                      piece.id
                                    );
                                  }
                                }}
                                className={`transcript-sentence ${pieceActive ? 'transcript-sentence-active' : ''} ${pieceHighlighted && !pieceActive ? 'transcript-sentence-match' : ''} ${pieceSaved ? 'transcript-sentence-saved' : ''}`}
                                aria-label={`Open passage at ${formatTimestamp(piece.startMs)}`}
                              >
                                {piece.text}
                              </span>{' '}
                            </span>
                          );
                        })}
                      </p>
                      {open && selectedPiece && (
                        <SectionActions
                          startMs={selectedPiece.startMs}
                          saved={selectedSaved}
                          onPlay={() =>
                            onPlayFrom(
                              selectedPiece.firstSegment,
                              selectedPiece.firstSegIndex,
                              selectedPiece.id
                            )
                          }
                          onCopyQuote={() =>
                            onCopyQuote(
                              selectedPiece.firstSegment,
                              selectedPiece.text,
                              selectedPiece.firstSegIndex
                            )
                          }
                          onCopyLink={() =>
                            onCopyLink(selectedPiece.firstSegment, selectedPiece.firstSegIndex)
                          }
                          onSave={() =>
                            onSaveMoment(
                              selectedPiece.firstSegment,
                              selectedPiece.firstSegIndex,
                              selectedPiece.text
                            )
                          }
                          onShare={
                            onSharePassage
                              ? () => onSharePassage(selectedPiece.firstSegment)
                              : undefined
                          }
                          onClose={onCloseSelection}
                        />
                      )}
                    </div>
                  </div>
                );
              })}
            </section>
          </Fragment>
        );
      })}
    </article>
  );
}

export default memo(FormattedTranscriptDocument);
