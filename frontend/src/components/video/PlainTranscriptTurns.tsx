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
    <div className="surface-card space-y-6" role="list" aria-label="Transcript paragraphs">
      {turns.map((turn) => {
        const activeEntry = turn.segments.find(({ id }) => id === activeSegId);

        return (
          <section
            key={turn.key}
            className={turn.speaker ? 'grid gap-3 sm:grid-cols-[8rem_1fr]' : 'block'}
            role="listitem"
          >
            {turn.speaker && <div className="font-semibold text-ink">{turn.speaker}:</div>}
            <div className="space-y-2 text-lg leading-8 text-ink">
              <p className="whitespace-normal font-serif text-[1.05rem]">
                {turn.segments.map(({ segment: seg, id, match }) => {
                  const saved = isSavedSegment(seg, id);

                  return (
                    <button
                      id={`seg-${id}`}
                      key={id}
                      type="button"
                      onClick={() => onClickSegment(seg, id)}
                      className={`mx-0.5 cursor-pointer rounded px-1 text-left leading-8 transition-colors hover:bg-surface-muted focus:bg-surface-muted ${
                        activeSegId === id || match ? 'bg-accent-soft ring-1 ring-accent' : ''
                      } ${saved ? 'ring-1 ring-warning' : ''}`}
                      aria-label={`Play ${turn.speaker ?? 'paragraph'} from ${msToHms(seg.start_ms)}`}
                    >
                      {seg.text.replace(/\s+/g, ' ').replace(/\s+([,.!?;:])/g, '$1').trim()}{' '}
                    </button>
                  );
                })}
              </p>
              {turn.segments.some(({ match }) => match) && (
                <div className="rounded bg-warning-soft p-2 text-xs text-ink" role="note">
                  <div className="mb-1 font-medium">Search match in this turn</div>
                  {turn.segments
                    .filter(({ match }) => match)
                    .map(({ match, id }) => (
                      <div key={id} className="prose prose-xs max-w-none" dangerouslySetInnerHTML={{ __html: match?.snippet ?? '' }} />
                    ))}
                </div>
              )}
              {activeEntry && (
                <div className="flex flex-wrap items-center gap-3 border-l-2 border-accent pl-3 text-sm">
                  <span className="text-xs uppercase tracking-wide text-subtle">Selected {formatTimestamp(activeEntry.segment.start_ms)}</span>
                  <button type="button" className="nav-link" onClick={() => onSaveMoment(activeEntry.segment, activeEntry.id, activeEntry.segment.text.replace(/\s+/g, ' ').replace(/\s+([,.!?;:])/g, '$1').trim())}>
                    Save moment
                  </button>
                  <button type="button" className="nav-link" onClick={() => onCopyQuote(activeEntry.segment, activeEntry.segment.text, activeEntry.id)}>
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
