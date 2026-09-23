import type { TranscriptBlock } from '../../types/api';
type Props = {
  source?: 'whisper' | 'youtube' | 'merged';
  sourceLabel?: string;
  blocks: TranscriptBlock[];
};

export default function TranscriptQualityNotice(props: Props) {
  void props;
  return (
    <div className="transcript-quality" role="note" aria-labelledby="transcript-quality-title">
      <span id="transcript-quality-title" className="font-semibold text-ink">
        Automated transcript
      </span>{' '}
      <span>
        Automated transcripts can contain errors in wording, speakers, and timestamp alignment.
        Treat timestamps as navigation aids and verify quotations against the linked source video.
      </span>
    </div>
  );
}
