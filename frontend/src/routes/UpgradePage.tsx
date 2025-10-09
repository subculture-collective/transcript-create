import { useSearchParams, Link } from 'react-router-dom'
import { useAuth, http } from '../services'

export default function UpgradePage() {
  const { user, login } = useAuth()
  const [params] = useSearchParams()
  const redirect = params.get('redirect') || '/'
  const reason = params.get('reason') || 'export'

  async function startCheckout(period: 'monthly' | 'yearly') {
    try {
      const { url } = await http.post('billing/checkout-session', { json: { period, redirect } }).json<{ url: string }>()
      if (url) location.href = url
    } catch (e) {
      console.error(e)
      alert('Billing not available yet.')
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="mb-2 text-2xl font-semibold">Upgrade to Pro</h1>
      {reason === 'export' && (
        <p className="mb-4 text-stone-600">Exports are a Pro feature. Upgrade to unlock SRT, VTT, JSON, and PDF downloads.</p>
      )}
      {!user ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-800">
          Please log in to continue. <button onClick={login} className="underline">Login</button>
        </div>
      ) : (
        <div className="flex gap-2">
          <button onClick={() => startCheckout('monthly')} className="inline-block rounded-md bg-stone-900 px-4 py-2 text-white">Go Pro Monthly</button>
          <button onClick={() => startCheckout('yearly')} className="inline-block rounded-md border px-4 py-2">Go Pro Yearly</button>
        </div>
      )}
      <div className="mt-4 text-sm">
        <Link to={redirect} className="text-stone-600 underline">Back to your video</Link>
      </div>
    </div>
  )
}
