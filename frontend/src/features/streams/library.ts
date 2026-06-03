import type { StreamLibraryFilters, VideoInfo } from '../../types/api';

export const DEFAULT_LIMIT = 24;

export const DATE_FIELD_OPTIONS = [
  { value: 'uploaded_at', label: 'Uploaded date' },
  { value: 'created_at', label: 'Created date' },
  { value: 'updated_at', label: 'Updated date' },
] as const;

export type DateField = NonNullable<StreamLibraryFilters['date_field']>;

export type FilterState = {
  q: string;
  completedOnly: boolean;
  dateField: DateField;
  dateFrom: string;
  dateTo: string;
  category: string;
};

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

export function formatDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date);
}

export function titleCase(value: string) {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function parseFilters(params: URLSearchParams): FilterState {
  const dateFieldParam = params.get('date_field');
  const dateField = DATE_FIELD_OPTIONS.some((option) => option.value === dateFieldParam)
    ? (dateFieldParam as DateField)
    : 'uploaded_at';

  return {
    q: params.get('q') ?? '',
    completedOnly: params.get('completed_only') === 'true',
    dateField,
    dateFrom: params.get('date_from') ?? '',
    dateTo: params.get('date_to') ?? '',
    category: params.get('category') ?? '',
  };
}

export function statusBadge(video: VideoInfo) {
  const states = [video.state, video.caption_ingest_state, video.diarization_state]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase());

  if (states.some((value) => /error|failed|cancel/.test(value))) {
    return { label: 'Needs attention', className: 'rounded-full bg-danger-soft px-2 py-1 font-medium text-danger' };
  }

  if (states.some((value) => /ready|complete|done|finished/.test(value))) {
    return { label: 'Ready', className: 'badge-success' };
  }

  if (states.some((value) => /process|queue|pending|transcrib|ingest|sync/.test(value))) {
    return { label: 'Processing', className: 'badge-warning' };
  }

  return {
    label: titleCase(video.state ?? 'Unknown'),
    className: 'rounded-full bg-surface-muted px-2 py-1 font-medium text-muted',
  };
}

export function dateFieldLabel(field: DateField) {
  return DATE_FIELD_OPTIONS.find((option) => option.value === field)?.label ?? titleCase(field);
}
