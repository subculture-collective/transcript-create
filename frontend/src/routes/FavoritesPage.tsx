import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { favorites, useAuth, apiListFavorites, apiDeleteFavorite } from '../services';

export default function FavoritesPage() {
  const { user } = useAuth();
  const [items, setItems] = useState(favorites.list());
  const [remote, setRemote] = useState<Array<{
    id: string;
    video_id: string;
    start_ms: number;
    end_ms: number;
    text?: string;
  }> | null>(null);
  useEffect(() => {
    if (user) {
      apiListFavorites()
        .then((r) => setRemote(r.items))
        .catch(() => setRemote(null));
    } else {
      setRemote(null);
    }
  }, [user]);
  useEffect(() => {
    if (!user) {
      const id = setInterval(() => setItems(favorites.list()), 1000);
      return () => clearInterval(id);
    }
  }, [user]);
  return (
    <div className="space-y-4">
      <h1 className="page-title">Favorites</h1>
      {user && remote !== null ? (
        remote.length === 0 ? (
          <p className="text-muted">No favorites yet.</p>
        ) : (
          <ul className="space-y-3">
            {remote.map((f) => (
              <li key={f.id} className="surface-card-compact flex items-start justify-between gap-4">
                <div>
                  <div className="mb-2 line-clamp-2">{f.text}</div>
                  <Link
                    className="action-link"
                    to={`/v/${f.video_id}?t=${Math.floor(f.start_ms / 1000)}`}
                  >
                    Open
                  </Link>
                </div>
                <button
                  className="cursor-pointer text-danger hover:underline"
                  onClick={async () => {
                    await apiDeleteFavorite(f.id).catch(() => {});
                    const next = await apiListFavorites().catch(() => null);
                    if (next) setRemote(next.items);
                  }}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )
      ) : (
        <>
          {items.length === 0 && <p className="text-muted">No favorites yet.</p>}
          <ul className="space-y-3">
            {items.map((f, i) => (
              <li key={i} className="surface-card-compact flex items-start justify-between gap-4">
                <div>
                  <div className="text-xs text-subtle">Segment {f.segIndex}</div>
                  <div className="mb-2 line-clamp-2">{f.text}</div>
                  <Link
                    className="action-link"
                    to={`/v/${f.videoId}?t=${Math.floor(f.startMs / 1000)}#seg-${f.segIndex}`}
                  >
                    Open
                  </Link>
                </div>
                <button
                  className="cursor-pointer text-danger hover:underline"
                  onClick={() => {
                    favorites.toggle(f);
                    setItems(favorites.list());
                  }}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
