import { Link } from 'react-router-dom';
import { useEpisodeIntelligence } from '../../features/videoTranscript/useEpisodeIntelligence';
import { buildTimestampLink, formatTimestamp } from '../../features/archive/format';

export default function EpisodeIntelligence({ videoId }: { videoId: string }) {
  const { related, quoted, error } = useEpisodeIntelligence(videoId);
  if (error)
    return (
      <div className="alert-warning" role="alert">
        Episode recommendations are temporarily unavailable.
      </div>
    );
  if (related === null || quoted === null)
    return (
      <div className="surface-card text-muted" role="status">
        Loading episode recommendations…
      </div>
    );
  return (
    <section className="grid gap-4" aria-label="Episode intelligence">
      <div className="surface-card space-y-3">
        <h2 className="section-title">Related episodes</h2>
        {related.length === 0 && <p className="text-muted">No explainable related episodes yet.</p>}
        {related.map((item) => (
          <article key={item.video.id} className="rounded-lg border border-border p-3">
            <Link className="font-semibold text-ink hover:text-accent" to={`/v/${item.video.id}`}>
              {item.video.title || 'Untitled VOD'}
            </Link>
            <div className="mt-2 flex flex-wrap gap-2">
              {item.reasons.map((reason) => (
                <span className="source-pill" key={reason}>
                  {reason}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
      <div className="surface-card space-y-3">
        <h2 className="section-title">Most-quoted moments</h2>
        {quoted.length === 0 && (
          <p className="text-muted">No quoted moments have accumulated yet.</p>
        )}
        {quoted.map((moment) => (
          <article
            key={`${moment.start_ms}:${moment.end_ms}`}
            className="rounded-lg border border-border p-3"
          >
            <Link className="action-link" to={buildTimestampLink(videoId, moment.start_ms)}>
              {formatTimestamp(moment.start_ms)} · quoted {moment.quote_count} times
            </Link>
            <p className="mt-2 text-sm text-muted">{moment.snippet}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
