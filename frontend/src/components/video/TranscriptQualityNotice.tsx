import type { TranscriptBlock } from '../../types/api';
import type { TranscriptSource } from '../../features/archive/format';

type Props = {
  source: TranscriptSource;
  sourceLabel?: string;
  blocks: TranscriptBlock[];
};

const sourceDefinitions: Record<TranscriptSource, string> = {
  whisper: 'Whisper speech-to-text generated from the archived audio.',
  youtube: 'Captions supplied by YouTube; they may be automatic or creator-provided.',
  merged: 'Whisper text aligned with available YouTube captions for comparison.',
};

export default function TranscriptQualityNotice({ source, sourceLabel, blocks }: Props) {
  const reviewCount = blocks.filter((block) => block.needs_review).length;
  return (
    <aside className="transcript-quality" aria-labelledby="transcript-quality-title">
      <div>
        <div className="archive-eyebrow">Transcript quality</div>
        <h3 id="transcript-quality-title" className="mt-1 text-base font-semibold text-ink">
          {sourceLabel ?? sourceDefinitions[source]}
        </h3>
      </div>
      <p className="text-sm leading-6 text-muted">
        Automated transcripts can contain errors in wording, speakers, and timestamp alignment.
        Treat timestamps as navigation aids and verify quotations against the linked source video.
      </p>
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="source-pill">Source: {source}</span>
        <span className={reviewCount > 0 ? 'badge-warning' : 'source-pill'}>
          {reviewCount > 0
            ? `${reviewCount} source disagreements flagged`
            : 'No source disagreement flags'}
        </span>
      </div>
    </aside>
  );
}
