import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import type {
  ArchivePersonAdminResponse,
  ArchiveVideoMetadataItem,
  ArchiveVideoTagAdminResponse,
} from '../types/api';

function mockJsonResponse<T>(value: T) {
  return {
    json: () => Promise.resolve(value),
  };
}

vi.mock('../services/api', () => ({
  http: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
  },
}));

import { http } from '../services/api';
import AdminVideoMetadata from '../routes/admin/AdminVideoMetadata';

describe('AdminVideoMetadata', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders editors, creates metadata, searches videos, and saves assignments', async () => {
    let people: ArchivePersonAdminResponse[] = [
      {
        id: 'person-1',
        slug: 'guest-one',
        display_name: 'Guest One',
        aliases: ['G1'],
        description: 'Frequent guest',
        status: 'published',
        sort_order: 1,
        created_at: '2026-06-01T00:00:00Z',
        updated_at: '2026-06-01T00:00:00Z',
      },
    ];
    let tags: ArchiveVideoTagAdminResponse[] = [
      {
        id: 'tag-1',
        slug: 'gaming',
        label: 'Gaming',
        kind: 'category',
        description: 'Gaming content',
        status: 'published',
        sort_order: 1,
        created_at: '2026-06-01T00:00:00Z',
        updated_at: '2026-06-01T00:00:00Z',
      },
    ];
    let videos: ArchiveVideoMetadataItem[] = [
      {
        id: 'video-1',
        youtube_id: 'abc123',
        title: 'Deep Dive with Guest One',
        people: [],
        tags: [],
      },
    ];

    vi.mocked(http.get).mockImplementation((url: any, options?: any) => {
      if (url === 'admin/archive/metadata/people') {
        return mockJsonResponse({ items: people }) as never;
      }
      if (url === 'admin/archive/metadata/tags') {
        return mockJsonResponse({ items: tags }) as never;
      }
      if (url === 'admin/archive/metadata/videos') {
        const searchParams: URLSearchParams | undefined = options?.searchParams;
        const query = searchParams?.get('q')?.toLowerCase() ?? '';
        const filtered = query
          ? videos.filter(
              (video) =>
                (video.title ?? '').toLowerCase().includes(query) || video.youtube_id.toLowerCase().includes(query)
            )
          : videos;
        return mockJsonResponse({ items: filtered, total: filtered.length }) as never;
      }
      return mockJsonResponse({ items: [] }) as never;
    });

    vi.mocked(http.post).mockImplementation((url: any, options?: any) => {
      if (url === 'admin/archive/metadata/people') {
        const payload = options?.json as Record<string, any>;
        const row = {
          id: `person-${people.length + 1}`,
          slug: payload.slug || payload.display_name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
          display_name: payload.display_name,
          aliases: payload.aliases ?? [],
          description: payload.description ?? null,
          status: payload.status ?? 'published',
          sort_order: payload.sort_order ?? 0,
          created_at: '2026-06-04T00:00:00Z',
          updated_at: '2026-06-04T00:00:00Z',
        };
        people = [row, ...people];
        return mockJsonResponse(row) as never;
      }

      if (url === 'admin/archive/metadata/tags') {
        const payload = options?.json as Record<string, any>;
        const row = {
          id: `tag-${tags.length + 1}`,
          slug: payload.slug || payload.label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
          label: payload.label,
          kind: payload.kind ?? 'category',
          description: payload.description ?? null,
          status: payload.status ?? 'published',
          sort_order: payload.sort_order ?? 0,
          created_at: '2026-06-04T00:00:00Z',
          updated_at: '2026-06-04T00:00:00Z',
        };
        tags = [row, ...tags];
        return mockJsonResponse(row) as never;
      }

      if (url === 'admin/archive/metadata/seed-tags') {
        tags = [
          ...tags,
          {
            id: 'tag-99',
            slug: 'okbuddy',
            label: 'Okbuddy',
            kind: 'category',
            description: 'Seeded tag',
            status: 'published',
            sort_order: 99,
            created_at: '2026-06-04T00:00:00Z',
            updated_at: '2026-06-04T00:00:00Z',
          },
        ];
        return mockJsonResponse({ created: 1 }) as never;
      }

      return mockJsonResponse({ ok: true }) as never;
    });

    vi.mocked(http.put).mockImplementation((url: any, options?: any) => {
      if (url === 'admin/archive/metadata/videos/video-1') {
        const payload = options?.json as {
          people: Array<{ slug: string; role?: string }>;
          tags: Array<{ slug: string }>;
        };
        const updated = {
          ...videos[0],
          people: payload.people.map((person) => ({
            slug: person.slug,
            display_name: people.find((entry) => entry.slug === person.slug)?.display_name || person.slug,
            aliases: [],
            description: null,
            role: person.role,
          })),
          tags: payload.tags.map((tag) => ({
            slug: tag.slug,
            label: tags.find((entry) => entry.slug === tag.slug)?.label || tag.slug,
            kind: tags.find((entry) => entry.slug === tag.slug)?.kind || 'category',
            description: null,
          })),
        };
        videos = [updated];
        return mockJsonResponse(updated) as never;
      }

      return mockJsonResponse({ ok: true }) as never;
    });

    render(
      <BrowserRouter>
        <AdminVideoMetadata />
      </BrowserRouter>
    );

    expect(await screen.findByText('Video metadata')).toBeInTheDocument();
    expect(await screen.findByText('Guest One')).toBeInTheDocument();
    expect(screen.getByText('Gaming')).toBeInTheDocument();

    const user = userEvent.setup();

    await user.type(screen.getByLabelText('Display name'), 'Guest Two');
    await user.type(screen.getByLabelText('Person slug'), 'guest-two');
    await user.type(screen.getByLabelText('Aliases'), 'GT');
    await user.type(screen.getByLabelText('Person description'), 'New guest');
    await user.click(screen.getByRole('button', { name: 'Create person' }));

    await waitFor(() => {
      expect(vi.mocked(http.post)).toHaveBeenCalledWith(
        'admin/archive/metadata/people',
        expect.objectContaining({
          json: expect.objectContaining({
            display_name: 'Guest Two',
            slug: 'guest-two',
            aliases: ['GT'],
            description: 'New guest',
            status: 'published',
          }),
        })
      );
    });
    expect(screen.getByText('Created Guest Two')).toBeInTheDocument();
    expect(screen.getByText('Guest Two')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Label'), 'React Notes');
    await user.type(screen.getByLabelText('Tag slug'), 'react-notes');
    await user.type(screen.getByLabelText('Tag description'), 'Frontend tag');
    await user.click(screen.getByRole('button', { name: 'Create tag' }));

    await waitFor(() => {
      expect(vi.mocked(http.post)).toHaveBeenCalledWith(
        'admin/archive/metadata/tags',
        expect.objectContaining({
          json: expect.objectContaining({
            label: 'React Notes',
            slug: 'react-notes',
            kind: 'category',
            description: 'Frontend tag',
            status: 'published',
          }),
        })
      );
    });
    expect(screen.getByText('Created React Notes')).toBeInTheDocument();
    expect(screen.getByText('React Notes')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Seed default tags' }));

    await waitFor(() => {
      expect(vi.mocked(http.post)).toHaveBeenCalledWith('admin/archive/metadata/seed-tags');
    });
    expect(screen.getByText('Seeded default tags.')).toBeInTheDocument();
    expect(await screen.findByText('Okbuddy')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Search videos'), 'abc123');
    await user.click(screen.getByRole('button', { name: 'Search videos' }));

    expect(await screen.findByText('Deep Dive with Guest One')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Select' }));

    expect(screen.getByText('Selected VOD')).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: 'Assign Guest Two' }));
    await user.click(screen.getByRole('checkbox', { name: 'Assign React Notes' }));

    await user.click(screen.getByRole('button', { name: 'Save assignment' }));

    await waitFor(() => {
      expect(vi.mocked(http.put)).toHaveBeenCalledWith(
        'admin/archive/metadata/videos/video-1',
        expect.objectContaining({
          json: expect.objectContaining({
            people: [{ slug: 'guest-two', role: 'guest' }],
            tags: [{ slug: 'react-notes' }],
          }),
        })
      );
    });

    expect(screen.getByText('Saved metadata assignment.')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Assign Guest Two' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Assign React Notes' })).toBeChecked();
  });
});
