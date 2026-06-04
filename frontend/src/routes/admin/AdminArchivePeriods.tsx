import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { http } from '../../services/api';
import type {
  ArchiveNamedPeriodAdminResponse,
  ArchiveNamedPeriodUpsertPayload,
} from '../../types/api';

type PeriodKind = 'week' | 'month' | 'event' | 'date' | 'holiday' | 'anniversary' | 'leadup' | 'fallout';
type PeriodStatus = 'published' | 'hidden';

const periodKinds: Array<{ value: 'all' | PeriodKind; label: string }> = [
  { value: 'all', label: 'All kinds' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'event', label: 'Event' },
  { value: 'date', label: 'Date' },
  { value: 'holiday', label: 'Holiday' },
  { value: 'anniversary', label: 'Anniversary' },
  { value: 'leadup', label: 'Leadup' },
  { value: 'fallout', label: 'Fallout' },
];

const statusOptions: Array<{ value: 'all' | PeriodStatus; label: string }> = [
  { value: 'all', label: 'All statuses' },
  { value: 'published', label: 'Published' },
  { value: 'hidden', label: 'Hidden' },
];

type PeriodFormState = {
  label: string;
  slug: string;
  kind: string;
  date_from: string;
  date_to: string;
  description: string;
  status: PeriodStatus;
  sort_order: string;
  recurring_month: string;
  recurring_day: string;
};

const emptyForm: PeriodFormState = {
  label: '',
  slug: '',
  kind: 'event',
  date_from: '',
  date_to: '',
  description: '',
  status: 'published',
  sort_order: '',
  recurring_month: '',
  recurring_day: '',
};

function formatDuration(seconds?: number | null) {
  if (!seconds && seconds !== 0) return '—';
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function formatDateTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatRecurringDate(row: Pick<ArchiveNamedPeriodAdminResponse, 'recurring_month' | 'recurring_day'>) {
  if (!row.recurring_month || !row.recurring_day) return null;
  const sample = new Date(Date.UTC(2024, row.recurring_month - 1, row.recurring_day));
  if (Number.isNaN(sample.getTime())) return `Every ${row.recurring_month}/${row.recurring_day}`;
  return `Every ${sample.toLocaleDateString(undefined, { month: 'long', day: 'numeric', timeZone: 'UTC' })}`;
}

function formatDateRange(row: Pick<ArchiveNamedPeriodAdminResponse, 'date_from' | 'date_to' | 'recurring_month' | 'recurring_day'>) {
  const recurring = formatRecurringDate(row);
  if (recurring) return recurring;
  if (row.date_from && row.date_to) return `${row.date_from} → ${row.date_to}`;
  return row.date_from || row.date_to || '—';
}

export default function AdminArchivePeriods() {
  const [items, setItems] = useState<ArchiveNamedPeriodAdminResponse[]>([]);
  const [q, setQ] = useState('');
  const [kind, setKind] = useState<'all' | PeriodKind>('all');
  const [status, setStatus] = useState<'all' | PeriodStatus>('all');
  const [form, setForm] = useState<PeriodFormState>(emptyForm);
  const [editingSlug, setEditingSlug] = useState('');
  const [appliedFilters, setAppliedFilters] = useState({
    q: '',
    kind: 'all' as 'all' | PeriodKind,
    status: 'all' as 'all' | PeriodStatus,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshingSlug, setRefreshingSlug] = useState('');
  const [seeding, setSeeding] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const fetchPeriods = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (appliedFilters.q) params.set('q', appliedFilters.q);
      if (appliedFilters.kind !== 'all') params.set('kind', appliedFilters.kind);
      if (appliedFilters.status !== 'all') params.set('status', appliedFilters.status);
      params.set('limit', '100');
      params.set('offset', '0');

      const response = await http
        .get('admin/archive/periods', { searchParams: params })
        .json<{ items: ArchiveNamedPeriodAdminResponse[] }>();
      setItems(response.items ?? []);
    } catch (fetchError) {
      console.error('Failed to load archive periods', fetchError);
      setError('Failed to load archive periods.');
    } finally {
      setLoading(false);
    }
  }, [appliedFilters]);

  useEffect(() => {
    void fetchPeriods();
  }, [fetchPeriods]);

  const beginEdit = (row: ArchiveNamedPeriodAdminResponse) => {
    setEditingSlug(row.slug);
    setForm({
      label: row.label ?? '',
      slug: row.slug ?? '',
      kind: row.kind ?? 'event',
      date_from: row.date_from ?? '',
      date_to: row.date_to ?? '',
      description: row.description ?? '',
      status: row.status === 'hidden' ? 'hidden' : 'published',
      sort_order: row.sort_order == null ? '' : String(row.sort_order),
      recurring_month: row.recurring_month == null ? '' : String(row.recurring_month),
      recurring_day: row.recurring_day == null ? '' : String(row.recurring_day),
    });
    setNotice(`Editing ${row.label}`);
    setError('');
  };

  const resetForm = () => {
    setEditingSlug('');
    setForm(emptyForm);
  };

  const refreshList = useCallback(async () => {
    await fetchPeriods();
  }, [fetchPeriods]);

  const applyFilters = () => {
    setAppliedFilters({ q: q.trim(), kind, status });
  };

  const submitForm = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setNotice('');

    const payload: ArchiveNamedPeriodUpsertPayload = {
      label: form.label.trim(),
      slug: form.slug.trim() || undefined,
      kind: form.kind.trim(),
      date_from: form.date_from,
      date_to: form.date_to,
      description: form.description.trim() || undefined,
      status: form.status,
    };
    const sortOrder = form.sort_order.trim() === '' ? undefined : Number(form.sort_order);
    if (sortOrder !== undefined && Number.isNaN(sortOrder)) {
      setSaving(false);
      setError('Sort order must be a number.');
      return;
    }
    if (sortOrder !== undefined) payload.sort_order = sortOrder;

    const recurringMonth = form.recurring_month.trim() === '' ? undefined : Number(form.recurring_month);
    const recurringDay = form.recurring_day.trim() === '' ? undefined : Number(form.recurring_day);
    if ((recurringMonth === undefined) !== (recurringDay === undefined)) {
      setSaving(false);
      setError('Recurring month and day must be set together.');
      return;
    }
    if (
      (recurringMonth !== undefined && (!Number.isInteger(recurringMonth) || recurringMonth < 1 || recurringMonth > 12)) ||
      (recurringDay !== undefined && (!Number.isInteger(recurringDay) || recurringDay < 1 || recurringDay > 31))
    ) {
      setSaving(false);
      setError('Recurring month/day must be valid numbers.');
      return;
    }
    if (recurringMonth !== undefined && recurringDay !== undefined) {
      payload.recurring_month = recurringMonth;
      payload.recurring_day = recurringDay;
    } else if (editingSlug) {
      payload.recurring_month = null;
      payload.recurring_day = null;
    }

    try {
      if (editingSlug) {
        await http.patch(`admin/archive/periods/${editingSlug}`, { json: payload }).json<ArchiveNamedPeriodAdminResponse>();
        setNotice(`Updated ${payload.label}`);
      } else {
        await http.post('admin/archive/periods', { json: payload }).json<ArchiveNamedPeriodAdminResponse>();
        setNotice(`Created ${payload.label}`);
      }
      resetForm();
      await refreshList();
    } catch (submitError) {
      console.error('Failed to save archive period', submitError);
      setError('Failed to save archive period.');
    } finally {
      setSaving(false);
    }
  };

  const toggleStatus = async (row: ArchiveNamedPeriodAdminResponse) => {
    setError('');
    setNotice('');
    const nextStatus = row.status === 'hidden' ? 'published' : 'hidden';

    try {
      await http
        .patch(`admin/archive/periods/${row.slug}`, { json: { status: nextStatus } })
        .json<ArchiveNamedPeriodAdminResponse>();
      setNotice(`${nextStatus === 'hidden' ? 'Hidden' : 'Published'} ${row.label}`);
      await refreshList();
    } catch (statusError) {
      console.error('Failed to update archive period status', statusError);
      setError('Failed to update period status.');
    }
  };

  const recalculate = async (row: ArchiveNamedPeriodAdminResponse) => {
    setRefreshingSlug(row.slug);
    setError('');
    setNotice('');

    try {
      await http.post(`admin/archive/periods/${row.slug}/refresh`).json<ArchiveNamedPeriodAdminResponse>();
      setNotice(`Recalculated ${row.label}`);
      await refreshList();
    } catch (refreshError) {
      console.error('Failed to recalculate archive period', refreshError);
      setError('Failed to recalculate period.');
    } finally {
      setRefreshingSlug('');
    }
  };

  const seedPeriods = async () => {
    setSeeding(true);
    setError('');
    setNotice('');

    try {
      const result = await http.post('admin/archive/periods/seed').json<Record<string, unknown>>();
      setNotice(`Seeded curated periods${Object.keys(result).length ? ` (${JSON.stringify(result)})` : ''}.`);
      await refreshList();
    } catch (seedError) {
      console.error('Failed to seed curated periods', seedError);
      setError('Failed to seed curated periods.');
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="page-title">Archive periods</h1>
        <p className="max-w-3xl text-sm text-muted">
          Create interesting days, anniversaries, holidays, leadups, and fallout windows that power the
          archive intelligence surface.
        </p>
      </div>

      <div className="surface-card space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-q">
              Search
            </label>
            <input
              id="period-q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="form-control min-w-72"
              placeholder="Label, slug, description"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-kind">
              Kind
            </label>
            <select
              id="period-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as 'all' | PeriodKind)}
              className="form-control min-w-48"
            >
              {periodKinds.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-status">
              Status
            </label>
            <select
              id="period-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as 'all' | PeriodStatus)}
              className="form-control min-w-44"
            >
              {statusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary" onClick={applyFilters} type="button">
            Apply
          </button>
          <button className="btn btn-secondary" onClick={seedPeriods} type="button" disabled={seeding}>
            {seeding ? 'Seeding…' : 'Seed curated periods'}
          </button>
        </div>
        {(notice || error) && (
          <div className="space-y-1 text-sm">
            {notice && <div className="text-success">{notice}</div>}
            {error && <div className="text-red-500">{error}</div>}
          </div>
        )}
      </div>

      <div className="surface-card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Create or edit a period</h2>
            <p className="text-sm text-muted">Use the form below to add a curated window or revise an existing one.</p>
          </div>
          {editingSlug && (
            <button className="btn btn-secondary" onClick={resetForm} type="button">
              Cancel edit
            </button>
          )}
        </div>

        <form className="grid gap-4 md:grid-cols-2" onSubmit={submitForm}>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-label">
              Label
            </label>
            <input
              id="period-label"
              required
              value={form.label}
              onChange={(e) => setForm((current) => ({ ...current, label: e.target.value }))}
              className="form-control"
              placeholder="January 6, 2021"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-slug">
              Slug
            </label>
            <input
              id="period-slug"
              value={form.slug}
              onChange={(e) => setForm((current) => ({ ...current, slug: e.target.value }))}
              className="form-control"
              placeholder="jan-6-2021"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-kind-form">
              Kind
            </label>
            <input
              id="period-kind-form"
              required
              value={form.kind}
              onChange={(e) => setForm((current) => ({ ...current, kind: e.target.value }))}
              className="form-control"
              list="period-kind-values"
              placeholder="event"
            />
            <datalist id="period-kind-values">
              {periodKinds.filter((option) => option.value !== 'all').map((option) => (
                <option key={option.value} value={option.value} />
              ))}
            </datalist>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-status-form">
              Status
            </label>
            <select
              id="period-status-form"
              value={form.status}
              onChange={(e) => setForm((current) => ({ ...current, status: e.target.value as PeriodStatus }))}
              className="form-control"
            >
              <option value="published">Published</option>
              <option value="hidden">Hidden</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-date-from">
              Date from
            </label>
            <input
              id="period-date-from"
              type="date"
              required
              value={form.date_from}
              onChange={(e) => setForm((current) => ({ ...current, date_from: e.target.value }))}
              className="form-control"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-date-to">
              Date to
            </label>
            <input
              id="period-date-to"
              type="date"
              required
              value={form.date_to}
              onChange={(e) => setForm((current) => ({ ...current, date_to: e.target.value }))}
              className="form-control"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-sort-order">
              Sort order
            </label>
            <input
              id="period-sort-order"
              type="number"
              value={form.sort_order}
              onChange={(e) => setForm((current) => ({ ...current, sort_order: e.target.value }))}
              className="form-control"
              placeholder="0"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-recurring-month">
              Recurring month
            </label>
            <input
              id="period-recurring-month"
              type="number"
              min={1}
              max={12}
              value={form.recurring_month}
              onChange={(e) => setForm((current) => ({ ...current, recurring_month: e.target.value }))}
              className="form-control"
              placeholder="8"
            />
            <p className="mt-1 text-xs text-muted">Set with recurring day for annual date periods like 8/21.</p>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-recurring-day">
              Recurring day
            </label>
            <input
              id="period-recurring-day"
              type="number"
              min={1}
              max={31}
              value={form.recurring_day}
              onChange={(e) => setForm((current) => ({ ...current, recurring_day: e.target.value }))}
              className="form-control"
              placeholder="21"
            />
            <p className="mt-1 text-xs text-muted">Recurring periods collect streams from that month/day across all years.</p>
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="period-description">
              Description
            </label>
            <textarea
              id="period-description"
              rows={4}
              value={form.description}
              onChange={(e) => setForm((current) => ({ ...current, description: e.target.value }))}
              className="form-control"
              placeholder="A concise explanation of why this window matters."
            />
          </div>
          <div className="md:col-span-2 flex items-center gap-3">
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? 'Saving…' : editingSlug ? 'Update period' : 'Create period'}
            </button>
            <button className="btn btn-secondary" type="button" onClick={resetForm}>
              Clear
            </button>
          </div>
        </form>
      </div>

      <div className="surface-card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Periods</h2>
            <p className="text-sm text-muted">Showing {items.length} curated windows.</p>
          </div>
          {loading && <div className="text-sm text-muted">Loading…</div>}
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted">
                <th className="px-2 py-2 text-left">Label</th>
                <th className="px-2 py-2 text-left">Slug</th>
                <th className="px-2 py-2 text-left">Kind</th>
                <th className="px-2 py-2 text-left">Dates</th>
                <th className="px-2 py-2 text-left">Status</th>
                <th className="px-2 py-2 text-left">Videos</th>
                <th className="px-2 py-2 text-left">Duration</th>
                <th className="px-2 py-2 text-left">Summary</th>
                <th className="px-2 py-2 text-left">Calculated</th>
                <th className="px-2 py-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id} className="border-b border-border align-top">
                  <td className="px-2 py-2 font-medium">{row.label}</td>
                  <td className="px-2 py-2 font-mono text-xs">{row.slug}</td>
                  <td className="px-2 py-2">{row.kind}</td>
                  <td className="px-2 py-2 whitespace-nowrap">{formatDateRange(row)}</td>
                  <td className="px-2 py-2">{row.status}</td>
                  <td className="px-2 py-2">{row.video_count}</td>
                  <td className="px-2 py-2 whitespace-nowrap">{formatDuration(row.total_duration_seconds)}</td>
                  <td className="px-2 py-2 max-w-md text-muted">{row.summary || row.description || '—'}</td>
                  <td className="px-2 py-2 whitespace-nowrap">{formatDateTime(row.calculated_at)}</td>
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap gap-2">
                      <button className="btn btn-secondary" type="button" onClick={() => beginEdit(row)}>
                        Edit
                      </button>
                      <button
                        className="btn btn-secondary"
                        type="button"
                        onClick={() => void recalculate(row)}
                        disabled={refreshingSlug === row.slug}
                      >
                        {refreshingSlug === row.slug ? 'Recalculating…' : 'Recalculate'}
                      </button>
                      <button className="btn btn-secondary" type="button" onClick={() => void toggleStatus(row)}>
                        {row.status === 'hidden' ? 'Publish' : 'Hide'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && items.length === 0 && (
                <tr>
                  <td className="px-2 py-6 text-center text-muted" colSpan={10}>
                    No periods found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
