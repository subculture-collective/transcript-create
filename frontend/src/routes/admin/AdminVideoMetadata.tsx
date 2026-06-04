import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { http } from '../../services/api';
import type {
  ArchivePerson,
  ArchivePersonAdminResponse,
  ArchivePersonUpsertPayload,
  ArchiveVideoAssignmentPayload,
  ArchiveVideoMetadataItem,
  ArchiveVideoMetadataListResponse,
  ArchiveVideoTag,
  ArchiveVideoTagAdminResponse,
  ArchiveVideoTagUpsertPayload,
} from '../../types/api';

type Status = 'published' | 'hidden';

type PersonFormState = {
  display_name: string;
  slug: string;
  aliases: string;
  description: string;
  status: Status;
  sort_order: string;
};

type TagFormState = {
  label: string;
  slug: string;
  kind: string;
  description: string;
  status: Status;
  sort_order: string;
};

const emptyPersonForm: PersonFormState = {
  display_name: '',
  slug: '',
  aliases: '',
  description: '',
  status: 'published',
  sort_order: '',
};

const emptyTagForm: TagFormState = {
  label: '',
  slug: '',
  kind: 'category',
  description: '',
  status: 'published',
  sort_order: '',
};

const tagKindOptions = ['category', 'topic', 'label', 'group'];

function normalizeItems<T>(value: T[] | { items?: T[] } | null | undefined): T[] {
  if (Array.isArray(value)) return value;
  return value?.items ?? [];
}

function parseAliases(raw: string) {
  return raw
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

function parseSortOrder(raw: string) {
  if (!raw.trim()) return undefined;
  const value = Number(raw);
  return Number.isNaN(value) ? null : value;
}

function asArchiveVideo(item: ArchiveVideoMetadataItem | { video?: ArchiveVideoMetadataItem; item?: ArchiveVideoMetadataItem } | null | undefined) {
  if (!item) return null;
  if ('video' in item && item.video) return item.video;
  if ('item' in item && item.item) return item.item;
  return item as ArchiveVideoMetadataItem;
}

function buildSelectionMap<T extends { slug: string }>(items: T[] | undefined) {
  return Object.fromEntries((items ?? []).map((item) => [item.slug, true]));
}

function chipList(items: Array<ArchivePerson | ArchiveVideoTag>, emptyLabel: string) {
  if (!items.length) {
    return <div className="text-sm text-muted">{emptyLabel}</div>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span key={item.slug} className="rounded-full border border-border bg-surface-muted px-2 py-1 text-xs text-muted">
          {'display_name' in item ? item.display_name : item.label}
        </span>
      ))}
    </div>
  );
}

export default function AdminVideoMetadata() {
  const [people, setPeople] = useState<ArchivePersonAdminResponse[]>([]);
  const [tags, setTags] = useState<ArchiveVideoTagAdminResponse[]>([]);
  const [personForm, setPersonForm] = useState<PersonFormState>(emptyPersonForm);
  const [tagForm, setTagForm] = useState<TagFormState>(emptyTagForm);
  const [editingPersonSlug, setEditingPersonSlug] = useState('');
  const [editingTagSlug, setEditingTagSlug] = useState('');
  const [peopleLoading, setPeopleLoading] = useState(true);
  const [tagsLoading, setTagsLoading] = useState(true);
  const [peopleSaving, setPeopleSaving] = useState(false);
  const [tagsSaving, setTagsSaving] = useState(false);
  const [videoQuery, setVideoQuery] = useState('');
  const [videoLimit, setVideoLimit] = useState('20');
  const [videoResults, setVideoResults] = useState<ArchiveVideoMetadataItem[]>([]);
  const [videoLoading, setVideoLoading] = useState(false);
  const [selectedVideo, setSelectedVideo] = useState<ArchiveVideoMetadataItem | null>(null);
  const [selectedPeople, setSelectedPeople] = useState<Record<string, boolean>>({});
  const [selectedPeopleRoles, setSelectedPeopleRoles] = useState<Record<string, string>>({});
  const [selectedTags, setSelectedTags] = useState<Record<string, boolean>>({});
  const [assignmentSaving, setAssignmentSaving] = useState(false);
  const [seedingTags, setSeedingTags] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const syncSelection = useCallback((video: ArchiveVideoMetadataItem) => {
    setSelectedPeople(buildSelectionMap(video.people));
    setSelectedPeopleRoles(
      Object.fromEntries((video.people ?? []).map((person) => [person.slug, person.role || 'guest']))
    );
    setSelectedTags(buildSelectionMap(video.tags));
  }, []);

  const loadPeople = useCallback(async () => {
    setPeopleLoading(true);
    try {
      const response = await http.get('admin/archive/metadata/people', { searchParams: { limit: '200', offset: '0' } }).json<
        ArchivePersonAdminResponse[] | { items?: ArchivePersonAdminResponse[] }
      >();
      setPeople(normalizeItems(response));
    } catch (loadError) {
      console.error('Failed to load archive people', loadError);
      setError('Failed to load people.');
    } finally {
      setPeopleLoading(false);
    }
  }, []);

  const loadTags = useCallback(async () => {
    setTagsLoading(true);
    try {
      const response = await http.get('admin/archive/metadata/tags', { searchParams: { limit: '200', offset: '0' } }).json<
        ArchiveVideoTagAdminResponse[] | { items?: ArchiveVideoTagAdminResponse[] }
      >();
      setTags(normalizeItems(response));
    } catch (loadError) {
      console.error('Failed to load archive tags', loadError);
      setError('Failed to load tags.');
    } finally {
      setTagsLoading(false);
    }
  }, []);

  const savePerson = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPeopleSaving(true);
    setError('');
    setNotice('');

    const payload: ArchivePersonUpsertPayload = {
      display_name: personForm.display_name.trim(),
      slug: editingPersonSlug ? undefined : personForm.slug.trim() || undefined,
      aliases: parseAliases(personForm.aliases),
      description: personForm.description.trim() || undefined,
      status: personForm.status,
    };
    const sortOrder = parseSortOrder(personForm.sort_order);
    if (sortOrder === null) {
      setPeopleSaving(false);
      setError('Person sort order must be a number.');
      return;
    }
    if (sortOrder !== undefined) payload.sort_order = sortOrder;

    try {
      const response = editingPersonSlug
        ? await http.patch(`admin/archive/metadata/people/${editingPersonSlug}`, { json: payload }).json<ArchivePersonAdminResponse>()
        : await http.post('admin/archive/metadata/people', { json: payload }).json<ArchivePersonAdminResponse>();

      setPeople((current) => {
        const withoutCurrent = current.filter((person) => person.slug !== editingPersonSlug);
        return [response, ...withoutCurrent];
      });
      setNotice(`${editingPersonSlug ? 'Updated' : 'Created'} ${response.display_name}`);
      setEditingPersonSlug('');
      setPersonForm(emptyPersonForm);
    } catch (saveError) {
      console.error('Failed to save archive person', saveError);
      setError('Failed to save person.');
    } finally {
      setPeopleSaving(false);
    }
  };

  const saveTag = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTagsSaving(true);
    setError('');
    setNotice('');

    const payload: ArchiveVideoTagUpsertPayload = {
      label: tagForm.label.trim(),
      slug: editingTagSlug ? undefined : tagForm.slug.trim() || undefined,
      kind: tagForm.kind.trim() || 'category',
      description: tagForm.description.trim() || undefined,
      status: tagForm.status,
    };
    const sortOrder = parseSortOrder(tagForm.sort_order);
    if (sortOrder === null) {
      setTagsSaving(false);
      setError('Tag sort order must be a number.');
      return;
    }
    if (sortOrder !== undefined) payload.sort_order = sortOrder;

    try {
      const response = editingTagSlug
        ? await http.patch(`admin/archive/metadata/tags/${editingTagSlug}`, { json: payload }).json<ArchiveVideoTagAdminResponse>()
        : await http.post('admin/archive/metadata/tags', { json: payload }).json<ArchiveVideoTagAdminResponse>();

      setTags((current) => {
        const withoutCurrent = current.filter((tag) => tag.slug !== editingTagSlug);
        return [response, ...withoutCurrent];
      });
      setNotice(`${editingTagSlug ? 'Updated' : 'Created'} ${response.label}`);
      setEditingTagSlug('');
      setTagForm(emptyTagForm);
    } catch (saveError) {
      console.error('Failed to save archive tag', saveError);
      setError('Failed to save tag.');
    } finally {
      setTagsSaving(false);
    }
  };

  const seedTags = async () => {
    setSeedingTags(true);
    setError('');
    setNotice('');

    try {
      await http.post('admin/archive/metadata/seed-tags').json<Record<string, unknown>>();
      setNotice('Seeded default tags.');
      await loadTags();
    } catch (seedError) {
      console.error('Failed to seed default tags', seedError);
      setError('Failed to seed default tags.');
    } finally {
      setSeedingTags(false);
    }
  };

  const searchVideos = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setVideoLoading(true);
    setError('');
    setNotice('');

    const params = new URLSearchParams();
    if (videoQuery.trim()) params.set('q', videoQuery.trim());
    params.set('limit', String(Number(videoLimit) > 0 ? Number(videoLimit) : 20));

    try {
      const response = await http.get('admin/archive/metadata/videos', { searchParams: params }).json<
        ArchiveVideoMetadataItem[] | ArchiveVideoMetadataListResponse
      >();
      const items = normalizeItems(response as ArchiveVideoMetadataItem[] | { items?: ArchiveVideoMetadataItem[] });
      setVideoResults(items);
      setNotice(items.length ? `Found ${items.length} VODs.` : 'No VODs matched your search.');
    } catch (searchError) {
      console.error('Failed to search archive videos', searchError);
      setError('Failed to search videos.');
    } finally {
      setVideoLoading(false);
    }
  };

  const selectVideo = (video: ArchiveVideoMetadataItem) => {
    setSelectedVideo(video);
    syncSelection(video);
    setNotice(`Selected ${video.title || video.youtube_id}`);
    setError('');
  };

  const saveAssignment = async () => {
    if (!selectedVideo) return;

    setAssignmentSaving(true);
    setError('');
    setNotice('');

    const payload: ArchiveVideoAssignmentPayload = {
      people: Object.entries(selectedPeople)
        .filter(([, checked]) => checked)
        .map(([slug]) => ({ slug, role: selectedPeopleRoles[slug]?.trim() || 'guest' })),
      tags: Object.entries(selectedTags)
        .filter(([, checked]) => checked)
        .map(([slug]) => ({ slug })),
    };

    try {
      const response = await http.put(`admin/archive/metadata/videos/${selectedVideo.id}`, { json: payload }).json<
        ArchiveVideoMetadataItem | { video?: ArchiveVideoMetadataItem; item?: ArchiveVideoMetadataItem }
      >();
      const updated = asArchiveVideo(response);
      if (updated) {
        setSelectedVideo(updated);
        syncSelection(updated);
        setVideoResults((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      }
      setNotice('Saved metadata assignment.');
    } catch (saveError) {
      console.error('Failed to save video metadata assignment', saveError);
      setError('Failed to save assignment.');
    } finally {
      setAssignmentSaving(false);
    }
  };

  const availablePeople = useMemo(() => people, [people]);
  const availableTags = useMemo(() => tags, [tags]);

  useEffect(() => {
    void loadPeople();
    void loadTags();
  }, [loadPeople, loadTags]);

  const editPerson = (row: ArchivePersonAdminResponse) => {
    setEditingPersonSlug(row.slug);
    setPersonForm({
      display_name: row.display_name,
      slug: row.slug,
      aliases: row.aliases?.join(', ') ?? '',
      description: row.description ?? '',
      status: row.status === 'hidden' ? 'hidden' : 'published',
      sort_order: row.sort_order == null ? '' : String(row.sort_order),
    });
    setError('');
    setNotice(`Editing ${row.display_name}`);
  };

  const editTag = (row: ArchiveVideoTagAdminResponse) => {
    setEditingTagSlug(row.slug);
    setTagForm({
      label: row.label,
      slug: row.slug,
      kind: row.kind,
      description: row.description ?? '',
      status: row.status === 'hidden' ? 'hidden' : 'published',
      sort_order: row.sort_order == null ? '' : String(row.sort_order),
    });
    setError('');
    setNotice(`Editing ${row.label}`);
  };

  const resetPersonForm = () => {
    setEditingPersonSlug('');
    setPersonForm(emptyPersonForm);
  };

  const resetTagForm = () => {
    setEditingTagSlug('');
    setTagForm(emptyTagForm);
  };

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="page-title">Video metadata</h1>
        <p className="max-w-3xl text-sm text-muted">
          Manage people, content tags, and VOD-level assignments from one admin screen.
        </p>
      </div>

      {(notice || error) && (
        <div className="surface-card space-y-1 text-sm" aria-live="polite">
          {notice && <div className="text-success" role="status">{notice}</div>}
          {error && <div className="text-red-500" role="alert">{error}</div>}
        </div>
      )}

      <section className="surface-card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">People</h2>
            <p className="text-sm text-muted">Create and maintain VOD-level people metadata.</p>
          </div>
          {peopleLoading && <div className="text-sm text-muted">Loading…</div>}
        </div>

        <form className="grid gap-4 md:grid-cols-2" onSubmit={savePerson}>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="person-display-name">
              Display name
            </label>
            <input
              id="person-display-name"
              required
              className="form-control"
              value={personForm.display_name}
              onChange={(event) => setPersonForm((current) => ({ ...current, display_name: event.target.value }))}
              placeholder="Guest One"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="person-slug">
              Person slug
            </label>
            <input
              id="person-slug"
              className="form-control"
              value={personForm.slug}
              onChange={(event) => setPersonForm((current) => ({ ...current, slug: event.target.value }))}
              placeholder="guest-one"
              disabled={Boolean(editingPersonSlug)}
            />
            {editingPersonSlug && <p className="mt-1 text-xs text-muted">Slugs are fixed after creation.</p>}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="person-aliases">
              Aliases
            </label>
            <input
              id="person-aliases"
              className="form-control"
              value={personForm.aliases}
              onChange={(event) => setPersonForm((current) => ({ ...current, aliases: event.target.value }))}
              placeholder="alt name, nickname"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="person-status">
              Person status
            </label>
            <select
              id="person-status"
              className="form-control"
              value={personForm.status}
              onChange={(event) => setPersonForm((current) => ({ ...current, status: event.target.value as Status }))}
            >
              <option value="published">Published</option>
              <option value="hidden">Hidden</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="person-sort-order">
              Person sort order
            </label>
            <input
              id="person-sort-order"
              className="form-control"
              type="number"
              value={personForm.sort_order}
              onChange={(event) => setPersonForm((current) => ({ ...current, sort_order: event.target.value }))}
              placeholder="0"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="person-description">
              Person description
            </label>
            <input
              id="person-description"
              className="form-control"
              value={personForm.description}
              onChange={(event) => setPersonForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="Short context about this person"
            />
          </div>
          <div className="md:col-span-2 flex flex-wrap items-center gap-3">
            <button className="btn btn-primary" type="submit" disabled={peopleSaving}>
              {peopleSaving ? 'Saving…' : editingPersonSlug ? 'Update person' : 'Create person'}
            </button>
            <button className="btn btn-secondary" type="button" onClick={resetPersonForm}>
              Clear
            </button>
          </div>
        </form>

        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted">
                <th className="px-2 py-2 text-left">Display name</th>
                <th className="px-2 py-2 text-left">Slug</th>
                <th className="px-2 py-2 text-left">Aliases</th>
                <th className="px-2 py-2 text-left">Description</th>
                <th className="px-2 py-2 text-left">Status</th>
                <th className="px-2 py-2 text-left">Sort</th>
                <th className="px-2 py-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {people.map((row) => (
                <tr key={row.id} className="border-b border-border align-top">
                  <td className="px-2 py-2 font-medium">{row.display_name}</td>
                  <td className="px-2 py-2 font-mono text-xs">{row.slug}</td>
                  <td className="px-2 py-2 text-muted">{row.aliases?.length ? row.aliases.join(', ') : '—'}</td>
                  <td className="px-2 py-2 text-muted">{row.description || '—'}</td>
                  <td className="px-2 py-2">{row.status}</td>
                  <td className="px-2 py-2">{row.sort_order}</td>
                  <td className="px-2 py-2">
                    <button className="btn btn-secondary" type="button" onClick={() => editPerson(row)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
              {!peopleLoading && people.length === 0 && (
                <tr>
                  <td className="px-2 py-6 text-center text-muted" colSpan={7}>
                    No people found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="surface-card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Tags</h2>
            <p className="text-sm text-muted">Create and manage content tags used on videos.</p>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn btn-secondary" type="button" onClick={seedTags} disabled={seedingTags}>
              {seedingTags ? 'Seeding…' : 'Seed default tags'}
            </button>
            {tagsLoading && <div className="text-sm text-muted">Loading…</div>}
          </div>
        </div>

        <form className="grid gap-4 md:grid-cols-2" onSubmit={saveTag}>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="tag-label">
              Label
            </label>
            <input
              id="tag-label"
              required
              className="form-control"
              value={tagForm.label}
              onChange={(event) => setTagForm((current) => ({ ...current, label: event.target.value }))}
              placeholder="Chadvice"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="tag-slug">
              Tag slug
            </label>
            <input
              id="tag-slug"
              className="form-control"
              value={tagForm.slug}
              onChange={(event) => setTagForm((current) => ({ ...current, slug: event.target.value }))}
              placeholder="chadvice"
              disabled={Boolean(editingTagSlug)}
            />
            {editingTagSlug && <p className="mt-1 text-xs text-muted">Slugs are fixed after creation.</p>}
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="tag-kind">
              Tag kind
            </label>
            <input
              id="tag-kind"
              className="form-control"
              value={tagForm.kind}
              list="tag-kind-values"
              onChange={(event) => setTagForm((current) => ({ ...current, kind: event.target.value }))}
              placeholder="category"
            />
            <datalist id="tag-kind-values">
              {tagKindOptions.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="tag-status">
              Tag status
            </label>
            <select
              id="tag-status"
              className="form-control"
              value={tagForm.status}
              onChange={(event) => setTagForm((current) => ({ ...current, status: event.target.value as Status }))}
            >
              <option value="published">Published</option>
              <option value="hidden">Hidden</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="tag-sort-order">
              Tag sort order
            </label>
            <input
              id="tag-sort-order"
              className="form-control"
              type="number"
              value={tagForm.sort_order}
              onChange={(event) => setTagForm((current) => ({ ...current, sort_order: event.target.value }))}
              placeholder="0"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="tag-description">
              Tag description
            </label>
            <input
              id="tag-description"
              className="form-control"
              value={tagForm.description}
              onChange={(event) => setTagForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="Short context about this tag"
            />
          </div>
          <div className="md:col-span-2 flex flex-wrap items-center gap-3">
            <button className="btn btn-primary" type="submit" disabled={tagsSaving}>
              {tagsSaving ? 'Saving…' : editingTagSlug ? 'Update tag' : 'Create tag'}
            </button>
            <button className="btn btn-secondary" type="button" onClick={resetTagForm}>
              Clear
            </button>
          </div>
        </form>

        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted">
                <th className="px-2 py-2 text-left">Label</th>
                <th className="px-2 py-2 text-left">Slug</th>
                <th className="px-2 py-2 text-left">Kind</th>
                <th className="px-2 py-2 text-left">Description</th>
                <th className="px-2 py-2 text-left">Status</th>
                <th className="px-2 py-2 text-left">Sort</th>
                <th className="px-2 py-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tags.map((row) => (
                <tr key={row.id} className="border-b border-border align-top">
                  <td className="px-2 py-2 font-medium">{row.label}</td>
                  <td className="px-2 py-2 font-mono text-xs">{row.slug}</td>
                  <td className="px-2 py-2">{row.kind}</td>
                  <td className="px-2 py-2 text-muted">{row.description || '—'}</td>
                  <td className="px-2 py-2">{row.status}</td>
                  <td className="px-2 py-2">{row.sort_order}</td>
                  <td className="px-2 py-2">
                    <button className="btn btn-secondary" type="button" onClick={() => editTag(row)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
              {!tagsLoading && tags.length === 0 && (
                <tr>
                  <td className="px-2 py-6 text-center text-muted" colSpan={7}>
                    No tags found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="surface-card space-y-4">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">Video assignment</h2>
          <p className="text-sm text-muted">Search a VOD, inspect current metadata, and update assignments.</p>
        </div>

        <form className="flex flex-wrap items-end gap-3" onSubmit={searchVideos}>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="video-search-q">
              Search videos
            </label>
            <input
              id="video-search-q"
              className="form-control w-full sm:min-w-80"
              value={videoQuery}
              onChange={(event) => setVideoQuery(event.target.value)}
              placeholder="Title or YouTube ID"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink" htmlFor="video-search-limit">
              Limit
            </label>
            <input
              id="video-search-limit"
              className="form-control w-28"
              type="number"
              min="1"
              value={videoLimit}
              onChange={(event) => setVideoLimit(event.target.value)}
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={videoLoading}>
            {videoLoading ? 'Searching…' : 'Search videos'}
          </button>
        </form>

        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted">
                <th className="px-2 py-2 text-left">Title</th>
                <th className="px-2 py-2 text-left">YouTube ID</th>
                <th className="px-2 py-2 text-left">Assigned people</th>
                <th className="px-2 py-2 text-left">Assigned tags</th>
                <th className="px-2 py-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {videoResults.map((row) => (
                <tr key={row.id} className={`border-b border-border align-top ${selectedVideo?.id === row.id ? 'bg-surface-muted' : ''}`}>
                  <td className="px-2 py-2 font-medium">{row.title || 'Untitled video'}</td>
                  <td className="px-2 py-2 font-mono text-xs">{row.youtube_id}</td>
                  <td className="px-2 py-2">{row.people?.length ?? 0}</td>
                  <td className="px-2 py-2">{row.tags?.length ?? 0}</td>
                  <td className="px-2 py-2">
                    <button className="btn btn-secondary" type="button" onClick={() => selectVideo(row)}>
                      Select
                    </button>
                  </td>
                </tr>
              ))}
              {!videoLoading && videoResults.length === 0 && (
                <tr>
                  <td className="px-2 py-6 text-center text-muted" colSpan={5}>
                    Search for a VOD to edit metadata.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="rounded-lg border border-border bg-surface-muted/40 p-4 space-y-4">
          {selectedVideo ? (
            <>
              <div className="space-y-1">
                <div className="text-sm uppercase tracking-wide text-muted">Selected VOD</div>
                <div className="text-base font-semibold">{selectedVideo.title || 'Untitled video'}</div>
                <div className="font-mono text-xs text-muted">{selectedVideo.youtube_id}</div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">Current people</h3>
                  {chipList(selectedVideo.people ?? [], 'No people assigned yet.')}
                </div>
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">Current tags</h3>
                  {chipList(selectedVideo.tags ?? [], 'No tags assigned yet.')}
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold">Assign people</h3>
                  <div className="space-y-2">
                    {availablePeople.map((person) => (
                      <label
                        key={person.id}
                        className="flex items-center gap-3 rounded border border-border bg-background px-3 py-2"
                      >
                        <input
                          type="checkbox"
                          aria-label={`Assign ${person.display_name}`}
                          checked={Boolean(selectedPeople[person.slug])}
                          onChange={(event) => {
                            const checked = event.target.checked;
                            setSelectedPeople((current) => ({ ...current, [person.slug]: checked }));
                            setSelectedPeopleRoles((current) => {
                              const next = { ...current };
                              if (checked) next[person.slug] = next[person.slug] || 'guest';
                              else delete next[person.slug];
                              return next;
                            });
                          }}
                        />
                        <span className="min-w-32 font-medium">{person.display_name}</span>
                        <span className="font-mono text-xs text-muted">{person.slug}</span>
                        <input
                          aria-label={`${person.display_name} role`}
                          className="form-control ml-auto w-32"
                          value={selectedPeopleRoles[person.slug] || 'guest'}
                          onChange={(event) =>
                            setSelectedPeopleRoles((current) => ({ ...current, [person.slug]: event.target.value }))
                          }
                          disabled={!selectedPeople[person.slug]}
                          placeholder="guest"
                        />
                      </label>
                    ))}
                    {!availablePeople.length && <div className="text-sm text-muted">Create people before assigning them.</div>}
                  </div>
                </div>

                <div className="space-y-3">
                  <h3 className="text-sm font-semibold">Assign tags</h3>
                  <div className="space-y-2">
                    {availableTags.map((tag) => (
                      <label
                        key={tag.id}
                        className="flex items-center gap-3 rounded border border-border bg-background px-3 py-2"
                      >
                        <input
                          type="checkbox"
                          aria-label={`Assign ${tag.label}`}
                          checked={Boolean(selectedTags[tag.slug])}
                          onChange={(event) =>
                            setSelectedTags((current) => ({ ...current, [tag.slug]: event.target.checked }))
                          }
                        />
                        <span className="min-w-32 font-medium">{tag.label}</span>
                        <span className="font-mono text-xs text-muted">{tag.slug}</span>
                        <span className="ml-auto text-xs text-muted">{tag.kind}</span>
                      </label>
                    ))}
                    {!availableTags.length && <div className="text-sm text-muted">Create tags before assigning them.</div>}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button className="btn btn-primary" type="button" onClick={() => void saveAssignment()} disabled={assignmentSaving}>
                  {assignmentSaving ? 'Saving…' : 'Save assignment'}
                </button>
              </div>
            </>
          ) : (
            <div className="text-sm text-muted">Search and select a VOD to edit its metadata.</div>
          )}
        </div>
      </section>
    </div>
  );
}
