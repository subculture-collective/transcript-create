import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { http } from '../../services/api';
import type {
  ArchiveLabelAssignmentListResponse,
  ArchiveLabelAssignmentResponse,
  ArchiveLabelExtractionResponse,
  ArchiveLabelListResponse,
  ArchiveLabelResponse,
  ArchiveLabelReviewAction,
} from '../../types/api';

type LabelAction = ArchiveLabelReviewAction['action'];

function normalizeItems<T>(value: T[] | { items?: T[] } | null | undefined): T[] {
  if (Array.isArray(value)) return value;
  return value?.items ?? [];
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function timestampLink(videoId: string, startMs?: number | null) {
  const seconds = Math.max(0, Math.floor((startMs ?? 0) / 1000));
  return `/v/${videoId}?t=${seconds}`;
}

function EvidencePreview({ evidence }: { evidence: Array<Record<string, unknown>> }) {
  if (!evidence.length) return <span className="text-muted">No evidence payloads</span>;

  return (
    <ul className="space-y-1 text-xs text-muted">
      {evidence.slice(0, 3).map((item, index) => {
        const text = typeof item.text === 'string' ? item.text : typeof item.snippet === 'string' ? item.snippet : JSON.stringify(item);
        return <li key={`${index}-${text.slice(0, 24)}`}>{text}</li>;
      })}
    </ul>
  );
}

export default function AdminLabelIntelligence() {
  const [labels, setLabels] = useState<ArchiveLabelResponse[]>([]);
  const [selectedLabel, setSelectedLabel] = useState<ArchiveLabelResponse | null>(null);
  const [assignments, setAssignments] = useState<ArchiveLabelAssignmentResponse[]>([]);
  const [statusFilter, setStatusFilter] = useState('candidate');
  const [query, setQuery] = useState('');
  const [loadingLabels, setLoadingLabels] = useState(true);
  const [loadingAssignments, setLoadingAssignments] = useState(false);
  const [savingAction, setSavingAction] = useState('');
  const [videoId, setVideoId] = useState('');
  const [extractionTier, setExtractionTier] = useState('cheap');
  const [extracting, setExtracting] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const loadLabels = useCallback(async () => {
    setLoadingLabels(true);
    setError('');
    const params = new URLSearchParams();
    if (statusFilter) params.set('status', statusFilter);
    if (query.trim()) params.set('q', query.trim());
    params.set('limit', '100');
    params.set('offset', '0');

    try {
      const response = await http.get('admin/archive/labels', { searchParams: params }).json<ArchiveLabelListResponse | ArchiveLabelResponse[]>();
      const items = normalizeItems(response);
      setLabels(items);
      setSelectedLabel((current) => {
        if (!current) return items[0] ?? null;
        return items.find((item) => item.id === current.id) ?? items[0] ?? null;
      });
    } catch (loadError) {
      console.error('Failed to load archive labels', loadError);
      setError('Failed to load labels.');
    } finally {
      setLoadingLabels(false);
    }
  }, [query, statusFilter]);

  const loadAssignments = useCallback(async (label: ArchiveLabelResponse | null) => {
    if (!label) {
      setAssignments([]);
      return;
    }

    setLoadingAssignments(true);
    setError('');
    try {
      const response = await http
        .get(`admin/archive/labels/${label.id}/assignments`, { searchParams: { limit: '100', offset: '0' } })
        .json<ArchiveLabelAssignmentListResponse | ArchiveLabelAssignmentResponse[]>();
      setAssignments(normalizeItems(response));
    } catch (loadError) {
      console.error('Failed to load label assignments', loadError);
      setError('Failed to load label assignments.');
    } finally {
      setLoadingAssignments(false);
    }
  }, []);

  useEffect(() => {
    void loadLabels();
  }, [loadLabels]);

  useEffect(() => {
    void loadAssignments(selectedLabel);
  }, [loadAssignments, selectedLabel]);

  const selectLabel = (label: ArchiveLabelResponse) => {
    setSelectedLabel(label);
    setNotice(`Selected ${label.label}`);
    setError('');
  };

  const refreshSelectedLabel = (updated: ArchiveLabelResponse) => {
    setLabels((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setSelectedLabel(updated);
  };

  const reviewLabel = async (action: LabelAction) => {
    if (!selectedLabel) return;
    const renameTo = action === 'rename' ? window.prompt('Rename label to', selectedLabel.label)?.trim() : undefined;
    if (action === 'rename' && !renameTo) return;
    const targetLabelId = action === 'merge' ? window.prompt('Target canonical label ID')?.trim() : undefined;
    if (action === 'merge' && !targetLabelId) return;

    setSavingAction(`label-${action}`);
    setError('');
    setNotice('');

    const payload: ArchiveLabelReviewAction = { action };
    if (renameTo) payload.label = renameTo;
    if (targetLabelId) payload.target_label_id = targetLabelId;

    try {
      const response = await http.post(`admin/archive/labels/${selectedLabel.id}/review`, { json: payload }).json<ArchiveLabelResponse>();
      refreshSelectedLabel(response);
      setNotice(`${action} applied to ${response.label}.`);
    } catch (saveError) {
      console.error('Failed to review archive label', saveError);
      setError(`Failed to ${action} label.`);
    } finally {
      setSavingAction('');
    }
  };

  const reviewAssignment = async (assignment: ArchiveLabelAssignmentResponse, action: Extract<LabelAction, 'approve' | 'reject' | 'publish' | 'hide'>) => {
    setSavingAction(`${assignment.id}-${action}`);
    setError('');
    setNotice('');

    try {
      const response = await http
        .post(`admin/archive/label-assignments/${assignment.id}/review`, { json: { action } satisfies ArchiveLabelReviewAction })
        .json<ArchiveLabelAssignmentResponse>();
      setAssignments((current) => current.map((item) => (item.id === response.id ? response : item)));
      refreshSelectedLabel(response.label);
      setNotice(`${action} applied to assignment.`);
    } catch (saveError) {
      console.error('Failed to review label assignment', saveError);
      setError(`Failed to ${action} assignment.`);
    } finally {
      setSavingAction('');
    }
  };

  const extractVideo = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!videoId.trim()) return;

    setExtracting(true);
    setError('');
    setNotice('');
    try {
      const response = await http
        .post(`admin/archive/labels/extract-video/${videoId.trim()}`, { searchParams: { extraction_tier: extractionTier } })
        .json<ArchiveLabelExtractionResponse>();
      setNotice(`Extraction queued for ${response.video_id}: ${response.candidates} candidates, ${response.assignments} assignments.`);
      await loadLabels();
    } catch (extractError) {
      console.error('Failed to extract labels for video', extractError);
      setError('Failed to extract labels for video.');
    } finally {
      setExtracting(false);
    }
  };

  const labelActions = useMemo<LabelAction[]>(() => ['publish', 'approve', 'reject', 'hide', 'rename', 'merge'], []);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="page-title">Label intelligence</h1>
        <p className="max-w-3xl text-sm text-muted">
          Review automatically extracted topics, recurring bits, entities, and evidence before publishing them into HasanAra discovery surfaces.
        </p>
      </div>

      {(notice || error) && (
        <div className="surface-card space-y-1 text-sm" aria-live="polite">
          {notice && <div className="text-success" role="status">{notice}</div>}
          {error && <div className="text-red-500" role="alert">{error}</div>}
        </div>
      )}

      <section className="surface-card space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Trigger extraction</h2>
          <p className="text-sm text-muted">Run the label extraction pipeline for a single VOD ID.</p>
        </div>
        <form className="grid gap-3 md:grid-cols-[1fr_160px_auto]" onSubmit={extractVideo}>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="label-video-id">Video ID</label>
            <input id="label-video-id" className="form-control" value={videoId} onChange={(event) => setVideoId(event.target.value)} placeholder="UUID" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="label-extraction-tier">Tier</label>
            <select id="label-extraction-tier" className="form-control" value={extractionTier} onChange={(event) => setExtractionTier(event.target.value)}>
              <option value="cheap">cheap</option>
              <option value="balanced">balanced</option>
              <option value="premium">premium</option>
            </select>
          </div>
          <button className="btn-primary self-end" type="submit" disabled={extracting || !videoId.trim()}>
            {extracting ? 'Extracting…' : 'Extract labels'}
          </button>
        </form>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
        <section className="surface-card space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Candidate labels queue</h2>
              <p className="text-sm text-muted">Filter labels by status or text.</p>
            </div>
            {loadingLabels && <div className="text-sm text-muted">Loading…</div>}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-ink" htmlFor="label-status-filter">Status</label>
              <select id="label-status-filter" className="form-control" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="candidate">candidate</option>
                <option value="published">published</option>
                <option value="hidden">hidden</option>
                <option value="rejected">rejected</option>
                <option value="merged">merged</option>
                <option value="">all</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-ink" htmlFor="label-search">Search labels</label>
              <input id="label-search" className="form-control" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="topic or slug" />
            </div>
          </div>

          <div className="max-h-[38rem] space-y-2 overflow-y-auto pr-1">
            {labels.length === 0 && !loadingLabels && <div className="rounded-md border border-border p-4 text-sm text-muted">No labels matched.</div>}
            {labels.map((label) => (
              <button
                key={label.id}
                type="button"
                className={`w-full rounded-lg border p-3 text-left transition ${selectedLabel?.id === label.id ? 'border-primary bg-primary/10' : 'border-border bg-surface hover:bg-surface-muted'}`}
                onClick={() => selectLabel(label)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium text-ink">{label.label}</div>
                    <div className="text-xs text-muted">{label.slug} · {label.kind}</div>
                  </div>
                  <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">{label.status}</span>
                </div>
                <div className="mt-2 text-xs text-muted">{label.source} · {label.publish_tier} · {formatPercent(label.confidence_score)}</div>
              </button>
            ))}
          </div>
        </section>

        <section className="surface-card space-y-5">
          {!selectedLabel ? (
            <div className="text-sm text-muted">Select a label to review its evidence and assignments.</div>
          ) : (
            <>
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Selected label detail</h2>
                  <div className="mt-1 text-2xl font-bold text-ink">{selectedLabel.label}</div>
                  <p className="text-sm text-muted">{selectedLabel.description || `${selectedLabel.slug} · ${selectedLabel.kind}`}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {labelActions.map((action) => (
                    <button key={action} className="btn-secondary" type="button" disabled={savingAction === `label-${action}`} onClick={() => void reviewLabel(action)}>
                      {action}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-3 text-sm sm:grid-cols-4">
                <div className="rounded-md border border-border p-3"><div className="text-muted">Status</div><div className="font-semibold">{selectedLabel.status}</div></div>
                <div className="rounded-md border border-border p-3"><div className="text-muted">Tier</div><div className="font-semibold">{selectedLabel.publish_tier}</div></div>
                <div className="rounded-md border border-border p-3"><div className="text-muted">Source</div><div className="font-semibold">{selectedLabel.source}</div></div>
                <div className="rounded-md border border-border p-3"><div className="text-muted">Confidence</div><div className="font-semibold">{formatPercent(selectedLabel.confidence_score)}</div></div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold">Evidence moments</h3>
                  {loadingAssignments && <span className="text-sm text-muted">Loading assignments…</span>}
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-border text-sm">
                    <thead className="text-left text-xs uppercase tracking-wide text-muted">
                      <tr>
                        <th className="py-2 pr-3">Moment</th>
                        <th className="py-2 pr-3">Status</th>
                        <th className="py-2 pr-3">Evidence</th>
                        <th className="py-2 pr-3">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {assignments.map((assignment) => (
                        <tr key={assignment.id}>
                          <td className="py-3 pr-3 align-top">
                            <Link className="text-primary underline-offset-2 hover:underline" to={timestampLink(assignment.video_id, assignment.start_ms)}>
                              {assignment.unit_type} · {Math.floor((assignment.start_ms ?? 0) / 1000)}s
                            </Link>
                            <div className="mt-1 text-xs text-muted">{formatPercent(assignment.confidence_score)} · {assignment.evidence_count} evidence</div>
                          </td>
                          <td className="py-3 pr-3 align-top"><span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">{assignment.status}</span></td>
                          <td className="py-3 pr-3 align-top"><EvidencePreview evidence={assignment.evidence} /></td>
                          <td className="py-3 pr-3 align-top">
                            <div className="flex flex-wrap gap-2">
                              {(['approve', 'reject', 'publish', 'hide'] as const).map((action) => (
                                <button
                                  key={action}
                                  className="btn-secondary px-2 py-1 text-xs"
                                  type="button"
                                  disabled={savingAction === `${assignment.id}-${action}`}
                                  onClick={() => void reviewAssignment(assignment, action)}
                                >
                                  {action}
                                </button>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {assignments.length === 0 && !loadingAssignments && <div className="rounded-md border border-border p-4 text-sm text-muted">No assignments for this label.</div>}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
