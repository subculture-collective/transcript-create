import { formatTimestamp } from '../../features/archive/format';

type Props = {
  startMs: number;
  saved: boolean;
  onPlay: () => void;
  onCopyQuote: () => void;
  onCopyLink: () => void;
  onSave: () => void;
  onShare?: () => void;
  onClose: () => void;
};

function Icon({ path }: { path: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={path} />
    </svg>
  );
}

const ICONS = {
  play: 'M7 4.5v15l12-7.5z',
  quote: 'M9 7H5v6h4v4l3-4V7zm10 0h-4v6h4v4l3-4V7z',
  link: 'M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1m2 5a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1',
  star: 'm12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z',
  share: 'M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7M16 6l-4-4-4 4m4-4v13',
  close: 'M6 6l12 12M18 6 6 18',
};

/** Actions for an opened transcript passage. */
export default function SectionActions({
  startMs,
  saved,
  onPlay,
  onCopyQuote,
  onCopyLink,
  onSave,
  onShare,
  onClose,
}: Props) {
  return (
    <div className="selection-toolbar" role="toolbar" aria-label="Passage actions">
      <button type="button" className="selection-action selection-action-primary" onClick={onPlay}>
        <Icon path={ICONS.play} />
        Play from here
        <span className="font-mono text-xs opacity-80">{formatTimestamp(startMs)}</span>
      </button>
      <button type="button" className="selection-action" onClick={onCopyQuote}>
        <Icon path={ICONS.quote} />
        Copy quote
      </button>
      <button type="button" className="selection-action" onClick={onCopyLink}>
        <Icon path={ICONS.link} />
        Copy link
      </button>
      <button
        type="button"
        className="selection-action"
        aria-pressed={saved}
        aria-label={saved ? 'Remove moment' : 'Save moment'}
        onClick={onSave}
      >
        <Icon path={ICONS.star} />
        {saved ? 'Saved' : 'Save'}
      </button>
      {onShare && (
        <button type="button" className="selection-action" onClick={onShare}>
          <Icon path={ICONS.share} />
          Share passage
        </button>
      )}
      <button
        type="button"
        className="selection-action ml-auto"
        onClick={onClose}
        aria-label="Close passage actions"
      >
        <Icon path={ICONS.close} />
      </button>
    </div>
  );
}
