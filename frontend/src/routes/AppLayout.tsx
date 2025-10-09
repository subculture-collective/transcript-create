import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../services'

export default function AppLayout() {
  const { user, loading, login, loginTwitch, logout } = useAuth()
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 font-serif">
      <header className="border-b">
        <div className="mx-auto flex max-w-7xl items-center justify-between p-4">
          <Link to="/" className="font-semibold tracking-tight">Transcript Search</Link>
          <nav className="flex items-center gap-4">
            <Link to="/" className="text-stone-600 hover:text-stone-900">Search</Link>
            <Link to="/favorites" className="text-stone-600 hover:text-stone-900">Favorites</Link>
            <Link to="/pricing" className="text-stone-600 hover:text-stone-900">Pricing</Link>
            {loading ? (
              <span className="text-stone-500">…</span>
            ) : user ? (
              <div className="flex items-center gap-3">
                {user.avatar_url && <img src={user.avatar_url} alt="avatar" className="h-6 w-6 rounded-full" />}
                <span className="text-stone-700">{user.name || user.email}</span>
                {user.plan === 'pro' && (
                  <>
                    <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">Pro</span>
                    <a href="/api/billing/portal" className="text-stone-600 hover:text-stone-900">Manage billing</a>
                  </>
                )}
                <button onClick={logout} className="text-stone-600 hover:text-stone-900">Logout</button>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <button onClick={login} className="text-stone-600 hover:text-stone-900">Login with Google</button>
                <span className="text-stone-400">|</span>
                <button onClick={loginTwitch} className="text-stone-600 hover:text-stone-900">Login with Twitch</button>
              </div>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl p-4">
        <Outlet />
      </main>
    </div>
  )
}
