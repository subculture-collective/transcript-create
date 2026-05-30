import type { ReactNode } from 'react';
import { useAuth } from '../services';

export default function Protected({ children }: { children: ReactNode }) {
  const { user, loading, login } = useAuth();
  if (loading) return <div className="p-6 text-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="p-6">
        <h2 className="mb-2 text-xl font-semibold">Sign in required</h2>
        <p className="mb-4 text-muted">Please sign in to access this page.</p>
        <button className="btn" onClick={login}>
          Sign in
        </button>
      </div>
    );
  }
  return <>{children}</>;
}
