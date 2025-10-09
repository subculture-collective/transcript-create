import { Link, Outlet } from 'react-router-dom'
import Protected from '../Protected'
import { useAuth } from '../../services/auth'

function ProtectedAdmin({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  // Simple admin check by email domain/flag can be surfaced from /auth/me if needed
  // For now, rely on backend to gate /admin endpoints; here we just require login
  if (loading) return <div className="p-6">Loading…</div>
  if (!user) return <Protected>{children}</Protected>
  return <>{children}</>
}

export default function AdminLayout() {
  return (
    <ProtectedAdmin>
      <div className="mx-auto max-w-7xl p-4">
        <nav className="mb-4 flex gap-4">
          <Link className="text-stone-700 hover:underline" to="/admin/events">Events</Link>
          <Link className="text-stone-700 hover:underline" to="/admin/users">Users</Link>
        </nav>
        <Outlet />
      </div>
    </ProtectedAdmin>
  )
}
