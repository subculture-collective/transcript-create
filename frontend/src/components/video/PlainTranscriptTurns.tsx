import type { Segment } from '../../types/api';
import type { TranscriptTurn } from '../../features/videoTranscript/transcript';
import { formatTimestamp } from '../../features/archive/format';

type Props = {
  turns: TranscriptTurn[];
  activeSegId: number | null;
  isSavedSegment: (segment: Segment, segIndex: number) => boolean;
  onClickSegment: (segment: Segment, id: number) => void;
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

export default function PlainTranscriptTurns({
  turns,
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

        return (
          <section key={turn.key} className="transcript-block" role="listitem">
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
                    <button
                      id={`seg-${id}`}
                      key={id}
                      type="button"
                      onClick={() => onClickSegment(seg, id)}
                      className={`transcript-sentence mx-0.5 text-left ${activeSegId === id ? 'transcript-sentence-active' : ''} ${match ? 'transcript-sentence-match' : ''} ${saved ? 'underline decoration-warning decoration-2 underline-offset-4' : ''}`}
                      aria-label={`Play ${turn.speaker ?? 'paragraph'} from ${msToHms(seg.start_ms)}`}
                    >
                      {seg.text
                        .replace(/\s+/g, ' ')
                        .replace(/\s+([,.!?;:])/g, '$1')
                        .trim()}{' '}
                    </button>
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
                      <div
                        key={id}
                        className="prose prose-xs max-w-none"
                        dangerouslySetInnerHTML={{ __html: match?.snippet ?? '' }}
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
                    Save moment
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
