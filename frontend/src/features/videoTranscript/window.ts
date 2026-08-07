export type TranscriptWindow = { start: number; end: number };

export function windowAroundIndex(total: number, index: number, size = 80): TranscriptWindow {
  const boundedTotal = Math.max(0, total);
  const boundedSize = Math.max(1, Math.min(size, boundedTotal || 1));
  if (boundedTotal <= boundedSize) return { start: 0, end: boundedTotal };

  const boundedIndex = Math.max(0, Math.min(index, boundedTotal - 1));
  const start = Math.max(
    0,
    Math.min(boundedIndex - Math.floor(boundedSize / 2), boundedTotal - boundedSize)
  );
  return { start, end: start + boundedSize };
}

export function ensureIndexVisible(
  total: number,
  index: number,
  current: TranscriptWindow,
  size = 80
) {
  if (index >= current.start && index < current.end) return current;
  return windowAroundIndex(total, index, size);
}
