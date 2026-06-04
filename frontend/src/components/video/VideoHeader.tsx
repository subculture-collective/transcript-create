import type { ReactNode } from 'react';

type Props = {
  title: string;
  actions?: ReactNode;
  children?: ReactNode;
};

export default function VideoHeader({
  title,
  actions,
  children,
}: Props) {
  return (
    <header className="surface-card space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="mb-1 text-sm font-medium uppercase tracking-wide text-subtle">VOD reader</p>
          <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h1>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2 text-sm">{actions}</div>}
      </div>
      {children}
    </header>
  );
}
