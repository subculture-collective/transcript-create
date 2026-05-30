import { useSearchParams, Link } from 'react-router-dom';
import { useAuth, http } from '../services';

export default function UpgradePage() {
  const { user, login } = useAuth();
  const [params] = useSearchParams();
  const redirect = params.get('redirect') || '/';
  const reason = params.get('reason') || 'export';

  async function startCheckout(period: 'monthly' | 'yearly') {
    try {
      const { url } = await http
        .post('billing/checkout-session', { json: { period, redirect } })
        .json<{ url: string }>();
      if (url) location.href = url;
    } catch (e) {
      console.error(e);
      alert('Billing not available yet.');
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="page-title">Upgrade to Pro</h1>
      {reason === 'export' && (
        <p className="text-muted">
          Exports are a Pro feature. Upgrade to unlock SRT, VTT, JSON, and PDF downloads.
        </p>
      )}
      {!user ? (
        <div className="alert-warning">
          Please log in to continue.{' '}
          <button onClick={login} className="cursor-pointer underline">
            Login
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => startCheckout('monthly')}
            className="btn-primary"
          >
            Go Pro Monthly
          </button>
          <button
            onClick={() => startCheckout('yearly')}
            className="btn-secondary"
          >
            Go Pro Yearly
          </button>
        </div>
      )}
      <div className="text-sm">
        <Link to={redirect} className="action-link">
          Back to your video
        </Link>
      </div>
    </div>
  );
}
