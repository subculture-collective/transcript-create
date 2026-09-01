import { Link } from 'react-router-dom';

const method = [
  ['Capture', 'Track public broadcasts and retain durable source metadata.'],
  ['Transcribe', 'Turn speech into timestamped text while preserving the source VOD.'],
  ['Structure', 'Add chapters, topics, and timelines without hiding the underlying transcript.'],
  ['Cite', 'Send every result back to the exact moment that supports it.'],
];

export default function AboutPage() {
  return (
    <div className="space-y-5 lg:space-y-7">
      <section className="archive-masthead">
        <div className="relative z-10 grid min-h-[29rem] gap-10 px-5 py-9 sm:px-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(19rem,0.65fr)] lg:items-end lg:px-12 lg:py-14">
          <div className="space-y-7">
            <div className="archive-eyebrow">About HasanAra</div>
            <h1 className="archive-display">A broadcast archive built like a public record.</h1>
            <p className="max-w-3xl text-lg leading-8 text-muted sm:text-xl">
              HasanAra makes long-form political livestreams legible: searchable transcripts,
              timestamped evidence, topic histories, and direct paths back to the original video.
            </p>
            <div className="flex flex-wrap gap-4 text-sm font-semibold">
              <Link to="/search" className="action-link">
                Search the archive →
              </Link>
              <Link to="/support" className="text-muted transition-colors hover:text-ink">
                Support the work
              </Link>
            </div>
          </div>
          <aside className="archive-section">
            <div className="archive-eyebrow">Project boundary</div>
            <p className="mt-4 text-lg font-semibold leading-7 text-ink">
              HasanAra is an independent Subcult project and is not affiliated with HasanAbi,
              Twitch, or YouTube.
            </p>
            <p className="mt-3 text-sm leading-6 text-muted">
              The archive indexes public broadcasts for research, discovery, and citation. Source
              creators retain their rights; links point viewers back to the original material.
            </p>
          </aside>
        </div>
      </section>

      <section className="archive-section">
        <div className="grid gap-8 lg:grid-cols-[15rem_1fr]">
          <div>
            <div className="archive-eyebrow">The method</div>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.045em] text-ink">
              Evidence before interpretation.
            </h2>
          </div>
          <ol className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2">
            {method.map(([title, copy], index) => (
              <li key={title} className="bg-surface p-6">
                <div className="font-mono text-xs text-accent">
                  {String(index + 1).padStart(2, '0')}
                </div>
                <h3 className="mt-8 text-xl font-semibold text-ink">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted">{copy}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="grid gap-5 md:grid-cols-3">
        <div className="archive-section md:col-span-2">
          <div className="archive-eyebrow">Editorial posture</div>
          <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-ink">
            Search results are leads, not verdicts.
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
            Automated transcripts and generated chapters can be wrong. HasanAra keeps the source,
            timestamps, and transcript context visible so readers can verify what was actually said.
            Corrections should improve the record without erasing its provenance.
          </p>
        </div>
        <div className="archive-section">
          <div className="archive-eyebrow">Built by</div>
          <p className="mt-3 text-xl font-semibold text-ink">Subcult</p>
          <p className="mt-2 text-sm leading-6 text-muted">
            Independent tools for culture, research, and collective memory.
          </p>
          <a href="https://subcult.tv" className="action-link mt-5 inline-flex text-sm">
            Visit Subcult ↗
          </a>
        </div>
      </section>
    </div>
  );
}
