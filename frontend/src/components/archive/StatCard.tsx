type StatCardProps = {
  label: string;
  value: string;
  className?: string;
  valueClassName?: string;
};

export default function StatCard({ label, value, className = '', valueClassName = 'mt-2 text-2xl font-semibold tracking-[-0.04em] text-ink' }: StatCardProps) {
  return (
    <div className={`rounded-lg border border-border/80 bg-surface-muted/70 p-4 ${className}`.trim()}>
      <div className="meta-label">{label}</div>
      <div className={valueClassName}>{value}</div>
    </div>
  );
}
