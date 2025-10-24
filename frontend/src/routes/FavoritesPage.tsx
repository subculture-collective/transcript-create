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
    <div>
      <h1 className="mb-4 text-2xl font-semibold">Favorites</h1>
      {user && remote !== null ? (
        remote.length === 0 ? (
          <p className="text-gray-600">No favorites yet.</p>
        ) : (
          <ul className="space-y-3">
            {remote.map((f) => (
              <li key={f.id} className="flex items-start justify-between gap-4 rounded border p-3">
                <div>
                  <div className="mb-2 line-clamp-2">{f.text}</div>
                  <Link
                    className="text-blue-600 hover:underline"
                    to={`/v/${f.video_id}?t=${Math.floor(f.start_ms / 1000)}`}
                  >
                    Open
                  </Link>
                </div>
                <button
                  className="text-red-600 hover:underline"
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
          {items.length === 0 && <p className="text-gray-600">No favorites yet.</p>}
          <ul className="space-y-3">
            {items.map((f, i) => (
              <li key={i} className="flex items-start justify-between gap-4 rounded border p-3">
                <div>
                  <div className="text-xs text-gray-500">Segment {f.segIndex}</div>
                  <div className="mb-2 line-clamp-2">{f.text}</div>
                  <Link
                    className="text-blue-600 hover:underline"
                    to={`/v/${f.videoId}?t=${Math.floor(f.startMs / 1000)}#seg-${f.segIndex}`}
                  >
                    Open
                  </Link>
                </div>
                <button
                  className="text-red-600 hover:underline"
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
