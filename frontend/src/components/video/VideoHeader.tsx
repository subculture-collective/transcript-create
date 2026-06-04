import type { ReactNode } from 'react';

type Props = {
  title: string;
  transcriptSourceLabel?: string | null;
  transcriptSource?: 'whisper' | 'youtube' | 'merged' | null;
  actions?: ReactNode;
  children?: ReactNode;
};

export default function VideoHeader({
  title,
  transcriptSourceLabel,
  transcriptSource,
  actions,
  children,
}: Props) {
  return (
    <header className="surface-card space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="mb-1 text-sm font-medium uppercase tracking-wide text-subtle">VOD transcript</p>
          <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h1>
          {transcriptSourceLabel && (
            <p className="mt-2 text-sm text-muted">
              Showing {transcriptSourceLabel}
              {transcriptSource === 'youtube' ? ' because Whisper is not available yet.' : ''}
            </p>
          )}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2 text-sm">{actions}</div>}
      </div>
      {children}
    </header>
  );
}
