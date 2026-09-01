import { Link } from 'react-router-dom';
import { buildTimestampLink } from '../../features/archive/format';
import type { TranscriptSource } from '../../features/archive/format';

type RemoteSavedMoment = {
  id: string;
  video_id: string;
  start_ms: number;
  end_ms: number;
  text?: string;
};

type LocalSavedMoment = {
  videoId: string;
  startMs: number;
  endMs: number;
  segIndex: number;
  text?: string;
  source?: TranscriptSource;
};

type SavedMomentItemProps =
  | {
      mode: 'remote';
      item: RemoteSavedMoment;
      onRemove: () => void;
    }
  | {
      mode: 'local';
      item: LocalSavedMoment;
      onRemove: () => void;
    };

export default function SavedMomentItem(props: SavedMomentItemProps) {
  if (props.mode === 'remote') {
    const { item, onRemove } = props;

    return (
      <li className="surface-card-compact flex items-start justify-between gap-4">
        <div>
          <div className="mb-2 line-clamp-2">{item.text}</div>
          <Link className="action-link" to={buildTimestampLink(item.video_id, item.start_ms)}>
            Open moment
          </Link>
        </div>
        <button className="nav-link text-danger" onClick={onRemove}>
          Remove
        </button>
      </li>
    );
  }

  const { item, onRemove } = props;

  return (
    <li className="surface-card-compact flex items-start justify-between gap-4">
      <div>
        <div className="text-xs text-subtle">Segment {item.segIndex}</div>
        <div className="mb-2 line-clamp-2">{item.text}</div>
        <Link
          className="action-link"
          to={buildTimestampLink(item.videoId, item.startMs, item.source ?? item.segIndex)}
        >
          Open moment
        </Link>
      </div>
      <button className="nav-link text-danger" onClick={onRemove}>
        Remove
      </button>
    </li>
  );
}
