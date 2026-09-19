import { buildTimestampLink } from '../archive/format';

export type PassageRange = { startMs: number; endMs: number };

export function parsePassageTime(value: string): number | null {
  if (!/^\d+(?::[0-5]\d){0,2}(?:\.\d{1,3})?$/.test(value.trim())) return null;
  const parts = value.trim().split(':').map(Number);
  const ms = Math.round(parts.reduce((seconds, part) => seconds * 60 + part, 0) * 1000);
  return Number.isSafeInteger(ms) ? ms : null;
}

export function formatPassageTime(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const fraction = ms % 1000 ? `.${String(ms % 1000).padStart(3, '0')}` : '';
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}${fraction}`;
}

export function passageRangeError(
  startMs: number | null,
  endMs: number | null,
  durationMs?: number
) {
  if (
    startMs === null ||
    endMs === null ||
    !Number.isSafeInteger(startMs) ||
    !Number.isSafeInteger(endMs) ||
    startMs < 0 ||
    endMs < 0
  )
    return 'Enter valid start and end times, such as 00:12:34.500.';
  if (endMs <= startMs) return 'End time must be after start time.';
  if (durationMs != null && durationMs > 0 && endMs > durationMs)
    return 'The passage must end within this recording.';
  return null;
}

export function buildPassageLink(videoId: string, range: PassageRange) {
  const url = new URL(buildTimestampLink(videoId, range.startMs), 'https://archive.invalid');
  url.searchParams.set('end_ms', String(range.endMs));
  return `${url.pathname}${url.search}${url.hash}`;
}

export function readPassageRange(params: URLSearchParams): PassageRange | null {
  const end = params.get('end_ms');
  const start = params.get('t_ms') ?? params.get('t');
  if (end === null) return null;
  // Reject malformed values instead of silently sharing a different passage.
  const startMs =
    start !== null && /^\d+(?:\.\d{1,3})?$/.test(start)
      ? Number(start) * (params.has('t_ms') ? 1 : 1000)
      : NaN;
  const endMs = /^\d+$/.test(end) ? Number(end) : NaN;
  return { startMs, endMs };
}

export function buildPassageShareLink(videoId: string, range: PassageRange) {
  return `/api/share/videos/${encodeURIComponent(videoId)}?${new URLSearchParams({ start_ms: String(range.startMs), end_ms: String(range.endMs) })}`;
}
