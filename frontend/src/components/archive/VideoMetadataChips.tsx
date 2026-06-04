export type VideoMetadataChip = {
  key: string;
  label: string;
};

type Props = {
  label: string;
  items: VideoMetadataChip[];
  limit?: number | null;
  className?: string;
};

export default function VideoMetadataChips({ label, items, limit = 3, className = 'flex flex-wrap gap-1.5' }: Props) {
  if (items.length === 0) return null;

  const visibleItems = limit == null ? items : items.slice(0, limit);
  const overflowCount = limit == null ? 0 : Math.max(0, items.length - visibleItems.length);

  return (
    <div role="group" aria-label={label} className={className}>
      {visibleItems.map((item) => (
        <span
          key={item.key}
          title={item.label}
          className="inline-flex max-w-full items-center rounded-md border border-border bg-surface-muted px-2 py-1 text-[11px] font-medium leading-none text-ink"
        >
          <span className="truncate">{item.label}</span>
        </span>
      ))}
      {overflowCount > 0 && (
        <span className="inline-flex items-center rounded-md border border-border bg-surface px-2 py-1 text-[11px] font-semibold leading-none text-subtle">
          +{overflowCount}
        </span>
      )}
    </div>
  );
}
