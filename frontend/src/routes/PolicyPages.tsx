import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

function PolicyPage({
  eyebrow,
  title,
  updated,
  children,
}: {
  eyebrow: string;
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <header className="archive-section py-10 sm:px-10">
        <div className="archive-eyebrow">{eyebrow}</div>
        <h1 className="mt-4 text-5xl font-semibold tracking-[-0.055em] text-ink">{title}</h1>
        <p className="mt-4 font-mono text-xs uppercase tracking-[0.18em] text-subtle">
          Last updated {updated}
        </p>
      </header>
      <article className="archive-section policy-copy py-9 sm:px-10">{children}</article>
    </div>
  );
}

export function PrivacyPage() {
  return (
    <PolicyPage eyebrow="Project policy" title="Privacy" updated="September 1, 2026">
      <h2>What works without an account</h2>
      <p>
        You can search, browse transcripts, open timelines, and follow source links without signing
        in. The archive records limited operational logs and aggregate usage events needed to
        secure, maintain, and improve the service.
      </p>
      <h2>Accounts and saved material</h2>
      <p>
        If you sign in with Google or Twitch, The archive receives the identity details that
        provider shares, such as a provider identifier, display name, email address, and avatar.
        Saved searches, moments, and account preferences are stored so they can be synchronized.
      </p>
      <h2>Donations</h2>
      <p>
        Stripe receives payment information when you use its hosted donation page. The archive does
        not collect or store complete card numbers. Stripe may share transaction identifiers,
        payment status, amount, contact details, and fraud-prevention signals needed to administer
        the contribution.
      </p>
      <h2>Your choices</h2>
      <p>
        You can browse anonymously, revoke sessions, unlink supported identity providers, and delete
        your archive account from the account page. Payment records may be retained where required
        for accounting, fraud prevention, or legal compliance.
      </p>
      <p>
        Questions about this policy can be raised through the operator listed on the{' '}
        <Link to="/about" className="action-link">
          about page
        </Link>
        .
      </p>
    </PolicyPage>
  );
}

export function TermsPage() {
  return (
    <PolicyPage eyebrow="Project policy" title="Terms" updated="September 1, 2026">
      <h2>Use of the archive</h2>
      <p>
        The archive is provided for research, discovery, commentary, and citation. Do not use the
        service to harass people, evade access controls, overload infrastructure, or misrepresent
        generated transcripts as infallible quotations.
      </p>
      <h2>Sources and accuracy</h2>
      <p>
        Broadcasts, channel marks, and linked media belong to their respective owners. Automated
        transcripts, chapters, topic labels, and search results can contain errors. Verify material
        against the linked source before relying on it.
      </p>
      <h2>Voluntary support</h2>
      <p>
        Donations are voluntary and do not purchase archive access, editorial control, or a service
        entitlement. Unless a receipt explicitly says otherwise, a contribution is not represented
        as a tax-deductible charitable donation. Payment processing is also subject to Stripe’s
        terms. Contact the project promptly if a payment was made in error.
      </p>
      <h2>Availability</h2>
      <p>
        The service is provided as available and may change, pause, or remove material to address
        security, legal, source, or operational concerns. These terms may be updated as the project
        develops; the date above identifies the current version.
      </p>
      <p>
        Read the{' '}
        <Link to="/privacy" className="action-link">
          privacy policy
        </Link>{' '}
        or learn more on the{' '}
        <Link to="/about" className="action-link">
          about page
        </Link>
        .
      </p>
    </PolicyPage>
  );
}
