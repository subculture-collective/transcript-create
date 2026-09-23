import type { Segment } from '../../types/api';
import {
  normalizeTranscriptText,
  type TranscriptTurn,
} from '../../features/videoTranscript/transcript';
import {
  canonicalMomentId,
  formatTimestamp,
  type TranscriptSource,
} from '../../features/archive/format';
import HighlightedSnippet from '../HighlightedSnippet';
import SectionActions from './SectionActions';

type Props = {
  turns: TranscriptTurn[];
  source: TranscriptSource;
  activeSegId: number | null;
  isSavedSegment: (segment: Segment, segIndex: number) => boolean;
  /** Opens (or closes) the passage actions for a segment. */
  onClickSegment: (segment: Segment, id: number) => void;
  onPlayFrom: (segment: Segment, id: number) => void;
  onCloseSelection: () => void;
  onSaveMoment: (segment: Segment, segIndex: number, text: string) => void;
  onSharePassage?: (segment: Segment) => void;
  onCopyQuote: (segment: Segment, text: string, segIndex: number) => void;
  onCopyLink: (segment: Segment, segIndex: number) => void;
};

export default function PlainTranscriptTurns({
  turns,
  source,
  activeSegId,
  isSavedSegment,
  onClickSegment,
  onPlayFrom,
  onCloseSelection,
  onSaveMoment,
  onCopyQuote,
  onCopyLink,
  onSharePassage,
}: Props) {
  return (
    <div className="transcript-document" role="list" aria-label="Transcript paragraphs">
      {turns.map((turn) => {
        const activeEntry = turn.segments.find(({ id }) => id === activeSegId);
        const activeEntrySaved = activeEntry
          ? isSavedSegment(activeEntry.segment, activeEntry.id)
          : false;

        return (
          <section
            key={turn.key}
            className="transcript-block transcript-paragraph content-auto"
            role="listitem"
            data-open={activeEntry ? 'true' : undefined}
          >
            <div className="transcript-block-meta">
              <button
                type="button"
                className="transcript-timecode"
                onClick={() =>
                  turn.segments[0] && onPlayFrom(turn.segments[0].segment, turn.segments[0].id)
                }
              >
                {turn.segments[0] ? formatTimestamp(turn.segments[0].segment.start_ms) : '—'}
              </button>
              {turn.speaker && <div className="transcript-speaker">{turn.speaker}</div>}
            </div>
            <div className="min-w-0 space-y-2">
              <p className="transcript-copy whitespace-normal">
                {turn.segments.map(({ segment: seg, id, match }) => {
                  const saved = isSavedSegment(seg, id);

                  return (
                    <span key={id}>
                      <span id={canonicalMomentId(source, seg.start_ms)} aria-hidden="true" />
                      <button
                        id={`seg-${id}`}
                        type="button"
                        data-transcript-sentence="true"
                        data-start-ms={seg.start_ms}
                        data-end-ms={seg.end_ms}
                        onClick={() => onClickSegment(seg, id)}
                        aria-expanded={activeSegId === id}
                        className={`transcript-sentence text-left ${activeSegId === id ? 'transcript-sentence-active' : ''} ${match ? 'transcript-sentence-match' : ''} ${saved ? 'transcript-sentence-saved' : ''}`}
                        aria-label={`Open ${turn.speaker ?? 'paragraph'} at ${formatTimestamp(seg.start_ms)}`}
                      >
                        {normalizeTranscriptText(seg.text)}{' '}
                      </button>
                    </span>
                  );
                })}
              </p>
              {turn.segments.some(({ match }) => match) && (
                <div
                  className="mt-2 rounded-xl border border-warning/25 bg-warning-soft p-3 text-xs text-ink"
                  role="note"
                >
                  <div className="mb-1 font-semibold uppercase tracking-[0.12em] text-warning">
                    Search match
                  </div>
                  {turn.segments
                    .filter(({ match }) => match)
                    .map(({ match, id }) => (
                      <HighlightedSnippet
                        key={id}
                        as="div"
                        className="prose prose-xs max-w-none"
                        snippet={match?.snippet ?? ''}
                        highlights={match?.highlights}
                      />
                    ))}
                </div>
              )}
              {activeEntry && (
                <SectionActions
                  startMs={activeEntry.segment.start_ms}
                  saved={activeEntrySaved}
                  onPlay={() => onPlayFrom(activeEntry.segment, activeEntry.id)}
                  onCopyQuote={() =>
                    onCopyQuote(activeEntry.segment, activeEntry.segment.text, activeEntry.id)
                  }
                  onCopyLink={() => onCopyLink(activeEntry.segment, activeEntry.id)}
                  onSave={() =>
                    onSaveMoment(
                      activeEntry.segment,
                      activeEntry.id,
                      normalizeTranscriptText(activeEntry.segment.text)
                    )
                  }
                  onShare={onSharePassage ? () => onSharePassage(activeEntry.segment) : undefined}
                  onClose={onCloseSelection}
                />
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
