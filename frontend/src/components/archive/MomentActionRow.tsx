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
    <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
      <Link
        to={buildTimestampLink(videoId, moment.start_ms, moment.source)}
        className="action-link"
        onClick={onOpenTimestamp}
      >
        Open at timestamp
      </Link>
      {query && (
        <Link to={buildPlayMatchesLink(videoId, moment, query)} className="action-link">
          Play from here
        </Link>
      )}
      <details className="moment-actions-menu">
        <summary>More actions</summary>
        <div className="moment-actions-popover">
          <button type="button" className="nav-link" onClick={onCopyTimestamp}>
            Copy timestamp
          </button>
          <button type="button" className="nav-link" onClick={onCopyQuote}>
            Copy quote
          </button>
          <button type="button" className="nav-link" disabled={saved} onClick={onSaveMoment}>
            {saved ? 'Saved moment' : 'Save moment'}
          </button>
          <Link to={`/v/${videoId}`} className="nav-link">
            Open full VOD
          </Link>
        </div>
      </details>
    </div>
  );
}
