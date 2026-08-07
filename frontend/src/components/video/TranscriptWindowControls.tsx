import type { TranscriptWindow } from '../../features/videoTranscript/window';

type Props = {
  range: TranscriptWindow;
  total: number;
  onMove: (direction: -1 | 1) => void;
};

export default function TranscriptWindowControls({ range, total, onMove }: Props) {
  if (total <= range.end - range.start) return null;

  return (
    <nav className="transcript-window-controls" aria-label="Transcript reading range">
      <button
        type="button"
        className="toolbar-button"
        disabled={range.start === 0}
        onClick={() => onMove(-1)}
      >
        Earlier transcript
      </button>
      <span className="font-mono text-[11px] text-subtle" aria-live="polite">
        Showing {range.start + 1}-{range.end} of {total} sections
      </span>
      <button
        type="button"
        className="toolbar-button"
        disabled={range.end >= total}
        onClick={() => onMove(1)}
      >
        Later transcript
      </button>
    </nav>
  );
}
