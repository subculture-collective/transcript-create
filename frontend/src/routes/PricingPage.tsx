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
    <div className="prose max-w-2xl">
      <h1>Pricing</h1>
      <p>Choose a plan that fits your workflow.</p>
      {redirect && !success && (
        <div className="rounded-md border border-sky-300 bg-sky-50 p-3 text-sky-800">
          After upgrading, we’ll send you back to your video.
        </div>
      )}
      {success && (
        <div className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-emerald-800">
          Thanks! Your Pro plan will activate shortly.
        </div>
      )}
      {canceled && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-800">
          Checkout canceled. You can try again anytime.
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border p-4">
          <h2 className="m-0">Free</h2>
          <p className="text-3xl font-semibold">$0</p>
          <ul>
            <li>5 searches per day</li>
            <li>Public favorites</li>
            <li>Previews</li>
          </ul>
        </div>
        <div className="rounded-lg border p-4">
          <h2 className="m-0">Pro</h2>
          <p className="text-3xl font-semibold">
            $9.99<span className="text-base font-normal">/mo</span>
          </p>
          <ul>
            <li>Unlimited search</li>
            <li>SRT/VTT/PDF exports</li>
            <li>Private notes & favorites</li>
            <li>Topic alerts & offline packs</li>
          </ul>
          <div className="flex gap-2">
            <button
              onClick={() => startCheckout('monthly')}
              className="inline-block rounded-md bg-stone-900 px-4 py-2 text-white"
            >
              Monthly
            </button>
            <button
              onClick={() => startCheckout('yearly')}
              className="inline-block rounded-md border px-4 py-2"
            >
              Yearly
            </button>
          </div>
          <button onClick={manageBilling} className="ml-2 inline-block rounded-md border px-4 py-2">
            Manage billing
          </button>
        </div>
      </div>
    </div>
  );
}
