import { useSite } from '../services/site';
import { Link } from 'react-router-dom';

const method = [
  ['Source records', 'Each public recording is tracked together with its source metadata.'],
  [
    'Transcripts',
    'Speech is transcribed automatically into timestamped text. The source VOD stays linked.',
  ],
  [
    'Chapters and topics',
    'Chapters, topics, and timelines are layered on top. The underlying transcript stays readable.',
  ],
  ['Timestamps', 'Every result links to the moment in the recording it came from.'],
];

export default function AboutPage() {
  const site = useSite();
  return (
    <div className="space-y-5 lg:space-y-7">
      <section className="archive-masthead">
        <div className="relative z-10 grid min-h-[29rem] gap-10 px-5 py-9 sm:px-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(19rem,0.65fr)] lg:items-end lg:px-12 lg:py-14">
          <div className="space-y-7">
            <div className="archive-eyebrow">About {site.name}</div>
            <h1 className="archive-display">
              Recordings, transcribed and linked back to their source.
            </h1>
            <p className="max-w-3xl text-lg leading-8 text-muted sm:text-xl">
              {site.name} keeps a timestamped transcript of each recording, indexes the text for
              search, groups mentions by topic, and links every result to its moment in the original
              video.
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
            <p className="mt-4 text-lg font-semibold leading-7 text-ink">{site.project_notice}</p>
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
              What is kept for each recording
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
          <div className="archive-eyebrow">Accuracy</div>
          <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-ink">
            Check the recording before you quote.
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
            Transcripts are produced automatically, and they and the generated chapters can be
            wrong. {site.name} keeps the source, timestamps, and surrounding transcript visible so
            readers can verify what was actually said. Corrections should fix the transcript without
            erasing its provenance.
          </p>
        </div>
        <div className="archive-section">
          <div className="archive-eyebrow">Built by</div>
          <p className="mt-3 text-xl font-semibold text-ink">{site.operator_name}</p>
          <p className="mt-2 text-sm leading-6 text-muted">{site.description}</p>
          {site.operator_url && (
            <a href={site.operator_url} className="action-link mt-5 inline-flex text-sm">
              Visit {site.operator_name} ↗
            </a>
          )}
        </div>
      </section>
    </div>
  );
}
