import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

type Props = {
  title: string;
  actions?: ReactNode;
  children?: ReactNode;
};

export default function VideoHeader({ title, actions, children }: Props) {
  return (
    <header className="episode-masthead">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 max-w-5xl">
          <div className="mb-4 flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-subtle">
            <Link to="/episodes" className="transition-colors hover:text-accent">
              Archive
            </Link>
            <span aria-hidden="true" className="text-border-strong">
              /
            </span>
            <span>Episode transcript</span>
            <span className="ml-1 inline-flex items-center gap-1.5 rounded-full border border-success/20 bg-success-soft px-2 py-1 text-[9px] tracking-[0.16em] text-success">
              <span className="h-1.5 w-1.5 rounded-full bg-success" aria-hidden="true" />
              Indexed
            </span>
          </div>
          <h1 className="max-w-4xl text-[clamp(2rem,4vw,4rem)] font-semibold leading-[0.98] tracking-[-0.055em] text-ink">
            {title}
          </h1>
        </div>
        {actions && (
          <div className="flex shrink-0 flex-wrap items-center gap-2 text-sm">{actions}</div>
        )}
      </div>
      {children && <div className="mt-6 border-t border-border/70 pt-5">{children}</div>}
    </header>
  );
}
