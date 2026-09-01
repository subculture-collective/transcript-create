const DATE_TIME_FORMAT = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
});

const MONTH_FORMAT = new Intl.DateTimeFormat(undefined, {
  month: 'long',
});

export function formatDuration(seconds?: number | null) {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
    : `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}

export function formatShortDuration(seconds?: number | null) {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.round((total % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes.toString().padStart(2, '0')}m`;
  return `${minutes}m`;
}

export function formatAggregateDuration(seconds?: number | null) {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  const hours = Math.max(0, seconds) / 3600;
  if (hours >= 1000)
    return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(hours / 1000)}k hours`;
  if (hours >= 100) return `${Math.round(hours).toLocaleString()} hours`;
  return formatShortDuration(seconds);
}

export function formatDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return DATE_FORMAT.format(date);
}

export function formatVideoTitle(title?: string | null, uploadedAt?: string | null) {
  const cleaned = title?.replace(/\s*[-–—]\s*$/, '').trim();
  if (cleaned) {
    const dateOnly = cleaned.match(
      /^(?:hasanabi\s+)?((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s+\d{4})$/i
    );
    return dateOnly ? `HasanAbi broadcast — ${dateOnly[1]}` : cleaned;
  }
  const date = formatDate(uploadedAt);
  return date === '—' ? 'Broadcast recording' : `Broadcast from ${date}`;
}
export function formatDateTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return DATE_TIME_FORMAT.format(date);
}

export function formatTimestamp(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600)
    .toString()
    .padStart(2, '0');
  const minutes = Math.floor((total % 3600) / 60)
    .toString()
    .padStart(2, '0');
  const seconds = (total % 60).toString().padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

export function formatMonthLabel(year: number, month: number) {
  return `${MONTH_FORMAT.format(new Date(year, Math.max(0, month - 1), 1))} ${year}`;
}

export function formatNumber(value?: number | null) {
  if (value == null || Number.isNaN(value)) return '0';
  return new Intl.NumberFormat(undefined).format(value);
}

export function buildMonthRange(year: number, month: number) {
  const start = new Date(Date.UTC(year, Math.max(0, month - 1), 1));
  const end = new Date(Date.UTC(year, month, 0, 23, 59, 59, 999));
  return {
    date_from: start.toISOString().slice(0, 10),
    date_to: end.toISOString().slice(0, 10),
  };
}

export type TranscriptSource = 'whisper' | 'youtube' | 'merged';

export function canonicalMomentId(_source: TranscriptSource, startMs: number) {
  return `moment-${Math.max(0, Math.floor(startMs))}`;
}

export function buildTimestampLink(
  videoId: string,
  startMs: number,
  _sourceOrSegmentId?: TranscriptSource | number
) {
  void _sourceOrSegmentId;
  const seconds = Math.max(0, Math.floor(startMs / 1000));
  const params = new URLSearchParams({ t: String(seconds) });
  if (startMs % 1000 !== 0) params.set('t_ms', String(Math.max(0, Math.floor(startMs))));
  return `/v/${videoId}?${params.toString()}#moment-${Math.max(0, Math.floor(startMs))}`;
}

export function titleCase(value: string) {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}
