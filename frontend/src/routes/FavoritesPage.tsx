import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { favorites } from '../services/favorites'

export default function FavoritesPage() {
  const [items, setItems] = useState(favorites.list())
  useEffect(() => {
    // naive polling to reflect changes from other pages
    const id = setInterval(() => setItems(favorites.list()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <div>
      <h1 className="mb-4 text-2xl font-semibold">Favorites</h1>
      {items.length === 0 && <p className="text-gray-600">No favorites yet.</p>}
      <ul className="space-y-3">
        {items.map((f, i) => (
          <li key={i} className="rounded border p-3">
            <div className="text-xs text-gray-500">Segment {f.segIndex}</div>
            <div className="mb-2 line-clamp-2">{f.text}</div>
            <Link className="text-blue-600 hover:underline" to={`/v/${f.videoId}?t=${Math.floor(f.startMs/1000)}#seg-${f.segIndex}`}>Open</Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
