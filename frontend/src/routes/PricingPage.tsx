import { http, useAuth } from '../services';
import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
// useAuth imported via services barrel
export default function PricingPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const success = params.get('success');
  const canceled = params.get('canceled');
  const redirect = params.get('redirect');
  // If we arrived with a redirect target and the user is Pro, send them back to where they came from
  useEffect(() => {
    if (user?.plan === 'pro' && redirect) {
      navigate(redirect, { replace: true });
    }
  }, [user?.plan, redirect, navigate]);
  async function startCheckout(period?: 'monthly' | 'yearly') {
    try {
      const body: { period?: string; redirect?: string } = {};
      if (period) body.period = period;
      if (redirect) body.redirect = redirect;
      const { url } = await http
        .post('billing/checkout-session', { json: body })
        .json<{ url: string }>();
      if (url) location.href = url;
    } catch (e) {
      console.error(e);
      alert('Billing not available yet.');
    }
  }
  async function manageBilling() {
    try {
      const { url } = await http.get('billing/portal').json<{ url: string }>();
      if (url) location.href = url;
    } catch (e) {
      console.error(e);
      alert('Billing not available yet.');
    }
  }
  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="page-title mb-2">Pricing</h1>
        <p className="text-muted">Choose a plan that fits your workflow.</p>
      </div>
      {redirect && !success && (
        <div className="alert-info">
          After upgrading, we’ll send you back to your video.
        </div>
      )}
      {success && (
        <div className="alert-success">
          Thanks! Your Pro plan will activate shortly.
        </div>
      )}
      {canceled && (
        <div className="alert-warning">
          Checkout canceled. You can try again anytime.
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="surface-card">
          <h2 className="section-title">Free</h2>
          <p className="text-3xl font-semibold">$0</p>
          <ul className="mt-4 space-y-2 text-muted">
            <li>5 searches per day</li>
            <li>Public favorites</li>
            <li>Previews</li>
          </ul>
        </div>
        <div className="surface-card border-accent">
          <h2 className="section-title">Pro</h2>
          <p className="text-3xl font-semibold">
            $9.99<span className="text-base font-normal">/mo</span>
          </p>
          <ul className="mt-4 space-y-2 text-muted">
            <li>Unlimited search</li>
            <li>SRT/VTT/PDF exports</li>
            <li>Private notes & favorites</li>
            <li>Topic alerts & offline packs</li>
          </ul>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={() => startCheckout('monthly')}
              className="btn-primary"
            >
              Monthly
            </button>
            <button
              onClick={() => startCheckout('yearly')}
              className="btn-secondary"
            >
              Yearly
            </button>
            <button onClick={manageBilling} className="btn-ghost">
              Manage billing
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
