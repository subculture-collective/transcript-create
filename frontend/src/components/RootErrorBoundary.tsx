/* eslint-disable react-refresh/only-export-components -- Error boundaries must be class components. */
import { Component, type ReactNode } from 'react';

function RouteErrorFallback() {
  return (
    <section className="mx-auto max-w-2xl p-8" role="alert">
      <div className="archive-eyebrow">Render error</div>
      <h1 className="mt-3 text-3xl font-semibold text-ink">Something went wrong</h1>
      <p className="mt-3 text-muted">An unexpected error occurred. Try refreshing the page.</p>
      <div className="mt-6 flex gap-3">
        <button className="btn" onClick={() => window.location.reload()}>
          Retry
        </button>
      </div>
    </section>
  );
}

export default class RootErrorBoundary extends Component<{ children: ReactNode }> {
  state: { hasError: boolean } = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, info: unknown) {
    console.error('Root ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) return <RouteErrorFallback />;
    return this.props.children;
  }
}
