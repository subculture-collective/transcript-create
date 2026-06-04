import { Link, Outlet } from 'react-router-dom';
import Protected from '../Protected';
import { useAuth } from '../../services/auth';

function ProtectedAdmin({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  // Simple admin check by email domain/flag can be surfaced from /auth/me if needed
  // For now, rely on backend to gate /admin endpoints; here we just require login
  if (loading) return <div className="p-6">Loading…</div>;
  if (!user) return <Protected>{children}</Protected>;
  return <>{children}</>;
}

export default function AdminLayout() {
  return (
    <ProtectedAdmin>
      <div className="mx-auto max-w-7xl space-y-6 p-4 md:p-6">
        <nav className="flex flex-wrap gap-2 border-b border-border pb-4">
          <Link className="nav-link rounded-md px-3 py-2" to="/admin/dashboard">
            Dashboard
          </Link>
          <Link className="nav-link rounded-md px-3 py-2" to="/admin/events">
            Events
          </Link>
          <Link className="nav-link rounded-md px-3 py-2" to="/admin/users">
            Users
          </Link>
          <Link className="nav-link rounded-md px-3 py-2" to="/admin/periods">
            Periods
          </Link>
          <Link className="nav-link rounded-md px-3 py-2" to="/admin/metadata">
            Metadata
          </Link>
          <Link className="nav-link rounded-md px-3 py-2" to="/admin/labels">
            Labels
          </Link>
        </nav>
        <Outlet />
      </div>
    </ProtectedAdmin>
  );
}
