type FavoriteKey = { videoId: string; segIndex: number };
export type FavoriteItem = FavoriteKey & { startMs: number; endMs: number; text: string };

const KEY = 'favorites:v1';

function load(): FavoriteItem[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as FavoriteItem[]) : [];
  } catch {
    return [];
  }
}

function save(items: FavoriteItem[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    // Suppress localStorage errors (e.g., quota exceeded)
  }
}

let cache = load();

export const favorites = {
  list(): FavoriteItem[] {
    return [...cache];
  },
  has(key: FavoriteKey): boolean {
    return cache.some((i) => i.videoId === key.videoId && i.segIndex === key.segIndex);
  },
  toggle(item: FavoriteItem) {
    if (this.has(item)) {
      cache = cache.filter((i) => !(i.videoId === item.videoId && i.segIndex === item.segIndex));
    } else {
      cache = [item, ...cache];
    }
    save(cache);
  },
};
