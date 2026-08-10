import { Link } from 'react-router-dom';
import type { SearchHit } from '../../types/api';
import { buildTimestampLink } from '../../features/archive/format';
import { buildPlayMatchesLink } from '../../features/search/moments';

type MomentActionRowProps = {
  videoId: string;
  moment: SearchHit;
  query: string;
  saved: boolean;
  onOpenTimestamp: () => void;
  onCopyTimestamp: () => void;
  onCopyQuote: () => void;
  onSaveMoment: () => void;
};

export default function MomentActionRow({
  videoId,
  moment,
  query,
  saved,
  onOpenTimestamp,
  onCopyTimestamp,
  onCopyQuote,
  onSaveMoment,
}: MomentActionRowProps) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-1 gap-y-2 border-t border-border/60 pt-3 text-xs">
      <Link
        to={buildTimestampLink(videoId, moment.start_ms, moment.source)}
        className="btn-secondary min-h-11 px-3 text-xs"
        onClick={onOpenTimestamp}
      >
        Open moment
      </Link>
      {query && (
        <Link
          to={buildPlayMatchesLink(videoId, moment, query)}
          className="btn-ghost min-h-11 px-2 text-xs text-accent"
        >
          Play from here
        </Link>
      )}
      <button type="button" className="btn-ghost min-h-11 px-2 text-xs" onClick={onCopyTimestamp}>
        Copy link
      </button>
      <button type="button" className="btn-ghost min-h-11 px-2 text-xs" onClick={onCopyQuote}>
        Copy quote
      </button>
      <button
        type="button"
        className="btn-ghost min-h-11 px-2 text-xs"
        aria-label={saved ? 'Saved moment' : 'Save moment'}
        disabled={saved}
        onClick={onSaveMoment}
      >
        {saved ? 'Saved' : 'Save'}
      </button>
      <Link to={`/v/${videoId}`} className="btn-ghost min-h-11 px-2 text-xs">
        Full VOD
      </Link>
    </div>
  );
}
