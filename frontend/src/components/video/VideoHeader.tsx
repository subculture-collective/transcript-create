import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

type Props = {
  title: string;
  facts?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
};

export default function VideoHeader({ title, facts, actions, children }: Props) {
  return (
    <>
      <header className="episode-header">
        <div className="min-w-0">
          <nav className="episode-crumbs" aria-label="Breadcrumb">
            <Link to="/episodes" className="transition-colors hover:text-accent">
              VODs
            </Link>
            <span aria-hidden="true">/</span>
            <span>Episode transcript</span>
          </nav>
          <h1 className="episode-title">{title}</h1>
          {facts && <div className="episode-facts">{facts}</div>}
        </div>
        {actions && <div className="episode-actions">{actions}</div>}
      </header>
      {children && (
        <details className="episode-details" open>
          <summary>Episode details</summary>
          <div>{children}</div>
        </details>
      )}
    </>
  );
}
