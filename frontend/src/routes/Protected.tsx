import type { ReactNode } from 'react'
import { useAuth } from '../services/auth'

export default function Protected({ children }: { children: ReactNode }) {
  const { user, loading, login } = useAuth()
  if (loading) return <div className="p-6 text-gray-600">Loading…</div>
  if (!user) {
    return (
      <div className="p-6">
        <h2 className="mb-2 text-xl font-semibold">Sign in required</h2>
        <p className="mb-4 text-gray-600">Please sign in to access this page.</p>
        <button className="btn" onClick={login}>Sign in</button>
      </div>
    )
  }
  return <>{children}</>
}
