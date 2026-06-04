import type { ArchiveSearchFilters, SearchHit } from '../../types/api';
import { formatTimestamp, sourceLabel } from '../../features/archive/format';
import MomentActionRow from './MomentActionRow';

type SearchMomentsListProps = {
  videoId: string;
  moments: SearchHit[];
  fallbackTitle: string;
  defaultSource?: ArchiveSearchFilters['source'];
  query: string;
  savedKeys: Set<string>;
  onSaveMoment: (videoId: string, moment: SearchHit, title: string) => void;
  onCopyTimestamp: (videoId: string, moment: SearchHit) => void;
  onCopyQuote: (videoId: string, moment: SearchHit, title: string) => void;
  onTrackResultClick: (videoId: string, moment: SearchHit) => void;
};

export default function SearchMomentsList({
  videoId,
  moments,
  fallbackTitle,
  defaultSource,
  query,
  savedKeys,
  onSaveMoment,
  onCopyTimestamp,
  onCopyQuote,
  onTrackResultClick,
}: SearchMomentsListProps) {
  return (
    <ul className="space-y-3">
      {moments.map((moment) => {
        const key = `${videoId}:${moment.start_ms}:${moment.end_ms}`;

        return (
          <li key={moment.id} className="group rounded-lg border border-border bg-surface-muted/80 p-4 transition-all hover:border-border-strong hover:bg-surface-muted/95">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <time className="timestamp-pill">
                {formatTimestamp(moment.start_ms)}–{formatTimestamp(moment.end_ms)}
              </time>
              <span className="source-pill">{sourceLabel(moment.source ?? defaultSource ?? 'best')}</span>
              {query && <span className="match-pill">match</span>}
            </div>
            <div className="archive-snippet" dangerouslySetInnerHTML={{ __html: moment.snippet }} />
            <MomentActionRow
              videoId={videoId}
              moment={moment}
              query={query}
              saved={savedKeys.has(key)}
              onOpenTimestamp={() => onTrackResultClick(videoId, moment)}
              onCopyTimestamp={() => onCopyTimestamp(videoId, moment)}
              onCopyQuote={() => onCopyQuote(videoId, moment, fallbackTitle)}
              onSaveMoment={() => onSaveMoment(videoId, moment, fallbackTitle)}
            />
            <p className="mt-3 text-xs text-subtle">{fallbackTitle}</p>
          </li>
        );
      })}
    </ul>
  );
}
