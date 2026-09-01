import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../services';
import type { SupportConfig } from '../types/api';

const fundingLines = [
  {
    number: '01',
    title: 'Keep the archive online',
    copy: 'Storage, backups, bandwidth, and the systems that keep thousands of broadcasts available.',
  },
  {
    number: '02',
    title: 'Turn broadcasts into a record',
    copy: 'Transcription, search indexing, chapter generation, and the ongoing work of citing every result.',
  },
  {
    number: '03',
    title: 'Keep access public',
    copy: 'No paywall around search, transcripts, timelines, or the source links behind a claim.',
  },
];

export default function SupportPage() {
  const [config, setConfig] = useState<SupportConfig | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .getSupportConfig()
      .then((next) => {
        if (active) setConfig(next);
      })
      .catch(() => {
        if (active) setUnavailable(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const donationsEnabled = config?.donations_enabled && config.payment_url;

  return (
    <div className="space-y-5 lg:space-y-7">
      <section className="archive-masthead overflow-hidden">
        <div className="relative z-10 grid min-h-[31rem] gap-10 px-5 py-9 sm:px-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.7fr)] lg:items-end lg:px-12 lg:py-14">
          <div className="max-w-4xl space-y-7">
            <div className="flex flex-wrap items-center gap-2">
              <span className="archive-eyebrow">Support HasanAra</span>
              <span className="source-pill">public infrastructure</span>
            </div>
            <h1 className="archive-display">Keep the public record searchable.</h1>
            <p className="max-w-2xl text-lg leading-8 text-muted sm:text-xl">
              HasanAra turns years of livestreams into a searchable, timestamped archive. Donations
              pay for the unglamorous machinery that keeps the record online, cited, and open.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              {donationsEnabled ? (
                <a
                  href={config.payment_url!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn min-h-12 px-6"
                >
                  Donate securely with Stripe ↗
                </a>
              ) : (
                <div
                  className="rounded-lg border border-border bg-surface-muted px-4 py-3 text-sm text-muted"
                  role="status"
                >
                  {unavailable
                    ? 'Donation status is temporarily unavailable.'
                    : config
                      ? 'Donations are not open yet. The archive remains public.'
                      : 'Checking donation status…'}
                </div>
              )}
              <Link to="/about" className="action-link text-sm font-semibold">
                How the archive works →
              </Link>
            </div>
          </div>

          <aside className="archive-section border-accent/25" aria-label="Project independence">
            <div className="archive-eyebrow">Independent project</div>
            <p className="mt-4 text-xl font-semibold leading-8 tracking-[-0.025em] text-ink">
              Built by Subcult. Not operated by or affiliated with HasanAbi, Twitch, or YouTube.
            </p>
            <p className="mt-4 text-sm leading-6 text-muted">
              A donation supports HasanAra’s hosting and research infrastructure. It does not buy
              editorial influence, special access, or content from the creator whose public
              broadcasts are indexed here.
            </p>
          </aside>
        </div>
      </section>

      <section className="archive-section">
        <div className="grid gap-8 lg:grid-cols-[minmax(14rem,0.45fr)_minmax(0,1fr)]">
          <div>
            <div className="archive-eyebrow">Where support goes</div>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.045em] text-ink">
              A small public utility with real operating costs.
            </h2>
          </div>
          <ol className="divide-y divide-border border-y border-border">
            {fundingLines.map((line) => (
              <li key={line.number} className="grid gap-3 py-6 sm:grid-cols-[3rem_14rem_1fr]">
                <span className="font-mono text-xs text-accent">{line.number}</span>
                <h3 className="font-semibold text-ink">{line.title}</h3>
                <p className="text-sm leading-6 text-muted">{line.copy}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="grid gap-5 md:grid-cols-2">
        <div className="archive-section">
          <div className="archive-eyebrow">Payment boundary</div>
          <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-ink">
            Card details never touch HasanAra.
          </h2>
          <p className="mt-3 text-sm leading-6 text-muted">
            The donation button opens a Stripe-hosted checkout. HasanAra receives confirmation from
            Stripe but does not collect or store your card number.
          </p>
        </div>
        <div className="archive-section">
          <div className="archive-eyebrow">No access tier</div>
          <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-ink">
            The archive stays public whether you donate or not.
          </h2>
          <p className="mt-3 text-sm leading-6 text-muted">
            Search, transcripts, episode pages, and cited source links remain available without a
            contribution. Support is voluntary.
          </p>
        </div>
      </section>
    </div>
  );
}
