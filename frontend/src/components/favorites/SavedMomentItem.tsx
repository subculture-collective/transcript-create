import { Link } from 'react-router-dom';

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
          <Link className="action-link" to={`/v/${item.video_id}?t=${Math.floor(item.start_ms / 1000)}`}>
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
        <Link className="action-link" to={`/v/${item.videoId}?t=${Math.floor(item.startMs / 1000)}#seg-${item.segIndex}`}>
          Open moment
        </Link>
      </div>
      <button className="nav-link text-danger" onClick={onRemove}>
        Remove
      </button>
    </li>
  );
}
