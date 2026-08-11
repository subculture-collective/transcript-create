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

type Props = {
  turns: TranscriptTurn[];
  source: TranscriptSource;
  activeSegId: number | null;
  isSavedSegment: (segment: Segment, segIndex: number) => boolean;
  onClickSegment: (segment: Segment, id: number) => void;
  onSaveMoment: (segment: Segment, segIndex: number, text: string) => void;
  onCopyQuote: (segment: Segment, text: string, segIndex: number) => void;
};

export default function PlainTranscriptTurns({
  turns,
  source,
  activeSegId,
  isSavedSegment,
  onClickSegment,
  onSaveMoment,
  onCopyQuote,
}: Props) {
  return (
    <div className="transcript-document" role="list" aria-label="Transcript paragraphs">
      {turns.map((turn) => {
        const activeEntry = turn.segments.find(({ id }) => id === activeSegId);
        const activeEntrySaved = activeEntry
          ? isSavedSegment(activeEntry.segment, activeEntry.id)
          : false;

        return (
          <section key={turn.key} className="transcript-block content-auto" role="listitem">
            <div className="transcript-block-meta">
              <button
                type="button"
                className="transcript-timecode"
                onClick={() =>
                  turn.segments[0] && onClickSegment(turn.segments[0].segment, turn.segments[0].id)
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
                        className={`transcript-sentence mx-0.5 text-left ${activeSegId === id ? 'transcript-sentence-active' : ''} ${match ? 'transcript-sentence-match' : ''} ${saved ? 'underline decoration-warning decoration-2 underline-offset-4' : ''}`}
                        aria-label={`Play ${turn.speaker ?? 'paragraph'} from ${formatTimestamp(seg.start_ms)}`}
                      >
                        {normalizeTranscriptText(seg.text)}{' '}
                      </button>
                    </span>
                  );
                })}
              </p>
              {turn.segments.some(({ match }) => match) && (
                <div
                  className="rounded-lg border border-warning/20 bg-warning-soft p-3 text-xs text-ink"
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
                <div className="selection-toolbar">
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
                    Selected · {formatTimestamp(activeEntry.segment.start_ms)}
                  </span>
                  <button
                    type="button"
                    className="selection-action"
                    onClick={() =>
                      onSaveMoment(
                        activeEntry.segment,
                        activeEntry.id,
                        activeEntry.segment.text
                          .replace(/\s+/g, ' ')
                          .replace(/\s+([,.!?;:])/g, '$1')
                          .trim()
                      )
                    }
                  >
                    {activeEntrySaved ? 'Remove moment' : 'Save moment'}
                  </button>
                  <button
                    type="button"
                    className="selection-action"
                    onClick={() =>
                      onCopyQuote(activeEntry.segment, activeEntry.segment.text, activeEntry.id)
                    }
                  >
                    Copy quote
                  </button>
                </div>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
