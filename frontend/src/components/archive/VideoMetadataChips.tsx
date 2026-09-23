import { Link } from 'react-router-dom';

export type VideoMetadataChip = {
  key: string;
  label: string;
};

type Props = {
  label: string;
  items: VideoMetadataChip[];
  limit?: number | null;
  className?: string;
  /** Link each chip, e.g. to its topic page. */
  hrefFor?: (label: string) => string;
};

export default function VideoMetadataChips({
  label,
  items,
  limit = 3,
  className = 'flex flex-wrap gap-1.5',
  hrefFor,
}: Props) {
  if (items.length === 0) return null;

  const visibleItems = limit == null ? items : items.slice(0, limit);
  const overflowCount = limit == null ? 0 : Math.max(0, items.length - visibleItems.length);

  return (
    <div role="group" aria-label={label} className={className}>
      {visibleItems.map((item) =>
        hrefFor ? (
          <Link key={item.key} to={hrefFor(item.label)} title={item.label} className="topic-chip">
            <span className="truncate">{item.label}</span>
          </Link>
        ) : (
          <span
            key={item.key}
            title={item.label}
            className="inline-flex max-w-full items-center rounded-full border border-border bg-surface-muted px-2.5 py-1 text-[11px] font-medium leading-none text-ink"
          >
            <span className="truncate">{item.label}</span>
          </span>
        )
      )}
      {overflowCount > 0 && (
        <span className="inline-flex items-center rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] font-semibold leading-none text-subtle">
          +{overflowCount}
        </span>
      )}
    </div>
  );
}
