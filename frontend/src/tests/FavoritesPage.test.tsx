import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axe from 'axe-core';
import FavoritesPage from '../routes/FavoritesPage';

const serviceMocks = vi.hoisted(() => ({
  user: null as null | { id: string },
  localMoments: [] as Array<{
    videoId: string;
    segIndex: number;
    startMs: number;
    endMs: number;
    text: string;
  }>,
  localSearches: [] as Array<{
    id: string;
    query: string;
    filters: Record<string, unknown>;
    created_at: string;
  }>,
  addFavorite: vi.fn(),
  createSavedSearch: vi.fn(),
  deleteFavorite: vi.fn(),
  deleteSavedSearch: vi.fn(),
  listFavorites: vi.fn(),
  listSavedSearches: vi.fn(),
  removeFavorite: vi.fn(),
  removeSavedSearch: vi.fn(),
  reloadFavorites: vi.fn(),
  reloadSavedSearches: vi.fn(),
  toggleFavorite: vi.fn(),
  addSavedSearch: vi.fn(),
}));

vi.mock('../services', () => ({
  useAuth: () => ({ user: serviceMocks.user }),
  favorites: {
    list: () => [...serviceMocks.localMoments],
    reload: serviceMocks.reloadFavorites,
    toggle: serviceMocks.toggleFavorite,
    remove: serviceMocks.removeFavorite,
  },
  localSavedSearches: {
    list: () => [...serviceMocks.localSearches],
    reload: serviceMocks.reloadSavedSearches,
    add: serviceMocks.addSavedSearch,
    remove: serviceMocks.removeSavedSearch,
  },
  savedSearchKey: (query: string, filters: Record<string, unknown>) =>
    JSON.stringify([
      query.trim(),
      filters.source ?? null,
      filters.category ?? null,
      filters.date_from ?? null,
      filters.date_to ?? null,
      filters.min_duration ?? null,
      filters.max_duration ?? null,
      filters.sort_by ?? null,
      filters.video_id ?? null,
      filters.limit ?? null,
      filters.offset ?? null,
    ]),
  apiAddFavorite: serviceMocks.addFavorite,
  apiCreateSavedSearch: serviceMocks.createSavedSearch,
  apiDeleteFavorite: serviceMocks.deleteFavorite,
  apiDeleteSavedSearch: serviceMocks.deleteSavedSearch,
  apiListFavorites: serviceMocks.listFavorites,
  apiListSavedSearches: serviceMocks.listSavedSearches,
}));

describe('FavoritesPage accessibility', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    serviceMocks.user = null;
    serviceMocks.localMoments = [];
    serviceMocks.localSearches = [];
    serviceMocks.reloadFavorites.mockImplementation(() => [...serviceMocks.localMoments]);
    serviceMocks.reloadSavedSearches.mockImplementation(() => [...serviceMocks.localSearches]);
  });

  it('keeps anonymous saved moments and searches accessible', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/saved?q=rent']}>
        <FavoritesPage />
      </MemoryRouter>
    );
    expect(screen.getByRole('heading', { name: 'Saved moments and searches' })).toBeInTheDocument();
    expect(screen.getByDisplayValue('rent')).toBeInTheDocument();
    expect((await axe.run(container)).violations).toEqual([]);
  });

  it('keeps anonymous saves local without calling synchronization APIs', async () => {
    serviceMocks.localMoments = [
      {
        videoId: 'video-local',
        segIndex: 1,
        startMs: 1_000,
        endMs: 2_000,
        text: 'Browser-only moment',
      },
    ];
    serviceMocks.localSearches = [
      {
        id: 'local:search-1',
        query: 'browser-only search',
        filters: {},
        created_at: '2026-08-06T00:00:00Z',
      },
    ];

    render(
      <MemoryRouter initialEntries={['/saved']}>
        <FavoritesPage />
      </MemoryRouter>
    );

    expect(screen.getByText('Browser-only moment')).toBeVisible();
    expect(screen.getByText('browser-only search')).toBeVisible();
    expect(serviceMocks.listFavorites).not.toHaveBeenCalled();
    expect(serviceMocks.listSavedSearches).not.toHaveBeenCalled();
    expect(serviceMocks.addFavorite).not.toHaveBeenCalled();
    expect(serviceMocks.createSavedSearch).not.toHaveBeenCalled();
  });

  it('migrates anonymous saves idempotently after sign-in', async () => {
    serviceMocks.user = { id: 'user-1' };
    serviceMocks.localMoments = [
      {
        videoId: 'video-1',
        segIndex: 1,
        startMs: 1_000,
        endMs: 2_000,
        text: 'Existing moment',
      },
      {
        videoId: 'video-2',
        segIndex: 2,
        startMs: 3_000,
        endMs: 4_000,
        text: 'New moment',
      },
    ];
    serviceMocks.localSearches = [
      {
        id: 'local:search-1',
        query: 'housing',
        filters: { source: 'best', category: 'politics' },
        created_at: '2026-08-06T00:00:00Z',
      },
    ];
    serviceMocks.listFavorites
      .mockResolvedValueOnce({
        items: [
          {
            id: 'remote-1',
            video_id: 'video-1',
            start_ms: 1_000,
            end_ms: 2_000,
            text: 'Existing moment',
          },
        ],
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 'remote-1',
            video_id: 'video-1',
            start_ms: 1_000,
            end_ms: 2_000,
            text: 'Existing moment',
          },
          {
            id: 'remote-2',
            video_id: 'video-2',
            start_ms: 3_000,
            end_ms: 4_000,
            text: 'New moment',
          },
        ],
      });
    serviceMocks.addFavorite.mockResolvedValue({ id: 'remote-2' });
    serviceMocks.listSavedSearches
      .mockResolvedValueOnce({
        items: [
          {
            id: 'remote-search-1',
            query: 'housing',
            filters: { category: 'politics', source: 'best' },
            created_at: '2026-08-05T00:00:00Z',
          },
        ],
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 'remote-search-1',
            query: 'housing',
            filters: { category: 'politics', source: 'best' },
            created_at: '2026-08-05T00:00:00Z',
          },
        ],
      });

    render(
      <MemoryRouter initialEntries={['/saved']}>
        <FavoritesPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(serviceMocks.listFavorites).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(serviceMocks.listSavedSearches).toHaveBeenCalledTimes(2));

    expect(serviceMocks.addFavorite).toHaveBeenCalledTimes(1);
    expect(serviceMocks.addFavorite).toHaveBeenCalledWith({
      video_id: 'video-2',
      start_ms: 3_000,
      end_ms: 4_000,
      text: 'New moment',
    });
    expect(serviceMocks.removeFavorite).toHaveBeenCalledTimes(2);
    expect(serviceMocks.createSavedSearch).not.toHaveBeenCalled();
    expect(serviceMocks.removeSavedSearch).toHaveBeenCalledWith('local:search-1');
  });

  it('renders and removes synchronized moments and searches', async () => {
    serviceMocks.user = { id: 'user-1' };
    const remoteMoment = {
      id: 'remote-1',
      video_id: 'video-1',
      start_ms: 12_000,
      end_ms: 18_000,
      text: 'Remote moment',
    };
    const remoteSearch = {
      id: 'search-1',
      query: 'housing',
      filters: { source: 'best', category: 'politics' },
      created_at: '2026-08-06T00:00:00Z',
    };
    serviceMocks.listFavorites
      .mockResolvedValueOnce({ items: [remoteMoment] })
      .mockResolvedValueOnce({ items: [remoteMoment] })
      .mockResolvedValueOnce({ items: [] });
    serviceMocks.listSavedSearches
      .mockResolvedValueOnce({ items: [remoteSearch] })
      .mockResolvedValueOnce({ items: [remoteSearch] })
      .mockResolvedValueOnce({ items: [] });
    serviceMocks.deleteFavorite.mockResolvedValue({ ok: true });
    serviceMocks.deleteSavedSearch.mockResolvedValue({ ok: true });
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/saved']}>
        <FavoritesPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('Remote moment')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Open moment' })).toHaveAttribute(
      'href',
      '/v/video-1?t=12'
    );
    expect(await screen.findByText('housing')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Reopen search' })).toHaveAttribute(
      'href',
      '/search?q=housing&source=best&category=politics'
    );

    await user.click(screen.getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(serviceMocks.deleteFavorite).toHaveBeenCalledWith('remote-1'));
    expect(await screen.findByText('No saved moments yet.')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(serviceMocks.deleteSavedSearch).toHaveBeenCalledWith('search-1'));
    expect(await screen.findByText('No saved searches yet.')).toBeVisible();
  });

  it('removes synchronized private data from the UI immediately after sign-out', async () => {
    serviceMocks.user = { id: 'user-1' };
    serviceMocks.listFavorites.mockResolvedValue({
      items: [
        {
          id: 'remote-1',
          video_id: 'video-private',
          start_ms: 12_000,
          end_ms: 18_000,
          text: 'Private synchronized moment',
        },
      ],
    });
    serviceMocks.listSavedSearches.mockResolvedValue({
      items: [
        {
          id: 'search-private',
          query: 'private synchronized search',
          filters: {},
          created_at: '2026-08-06T00:00:00Z',
        },
      ],
    });

    const view = render(
      <MemoryRouter initialEntries={['/saved']}>
        <FavoritesPage />
      </MemoryRouter>
    );
    expect(await screen.findByText('Private synchronized moment')).toBeVisible();
    expect(await screen.findByText('private synchronized search')).toBeVisible();

    serviceMocks.user = null;
    view.rerender(
      <MemoryRouter initialEntries={['/saved']}>
        <FavoritesPage />
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(screen.queryByText('Private synchronized moment')).not.toBeInTheDocument()
    );
    expect(screen.queryByText('private synchronized search')).not.toBeInTheDocument();
    expect(screen.getByText('No saved moments yet.')).toBeVisible();
    expect(screen.getByText('No saved searches yet.')).toBeVisible();
  });

  it('preserves local saves when sign-in synchronization fails', async () => {
    serviceMocks.user = { id: 'user-1' };
    serviceMocks.localMoments = [
      {
        videoId: 'video-local',
        segIndex: 3,
        startMs: 7_000,
        endMs: 9_000,
        text: 'Unsynchronized moment',
      },
    ];
    serviceMocks.localSearches = [
      {
        id: 'local:search-1',
        query: 'unsynchronized search',
        filters: {},
        created_at: '2026-08-06T00:00:00Z',
      },
    ];
    serviceMocks.listFavorites.mockResolvedValue({ items: [] });
    serviceMocks.addFavorite.mockRejectedValue(new Error('offline'));
    serviceMocks.listSavedSearches.mockResolvedValue({ items: [] });
    serviceMocks.createSavedSearch.mockRejectedValue(new Error('offline'));

    render(
      <MemoryRouter initialEntries={['/saved']}>
        <FavoritesPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('Unsynchronized moment')).toBeVisible();
    expect(screen.getByText('unsynchronized search')).toBeVisible();
    await waitFor(() => expect(serviceMocks.addFavorite).toHaveBeenCalled());
    await waitFor(() => expect(serviceMocks.createSavedSearch).toHaveBeenCalled());
    expect(serviceMocks.removeFavorite).not.toHaveBeenCalled();
    expect(serviceMocks.removeSavedSearch).not.toHaveBeenCalled();
  });

  it('saves a filtered search remotely and disables duplicate submission while saving', async () => {
    serviceMocks.user = { id: 'user-1' };
    serviceMocks.listFavorites.mockResolvedValue({ items: [] });
    const saved = {
      id: 'search-1',
      query: 'rent',
      filters: { source: 'youtube', date_from: '2026-01-01' },
      created_at: '2026-08-06T00:00:00Z',
    };
    serviceMocks.listSavedSearches
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [saved] });
    let resolveSave: ((value: typeof saved) => void) | undefined;
    serviceMocks.createSavedSearch.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSave = resolve;
        })
    );
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/saved?q=rent&source=youtube&date_from=2026-01-01']}>
        <FavoritesPage />
      </MemoryRouter>
    );

    await user.click(screen.getByRole('button', { name: 'Save search' }));
    const savingButton = screen.getByRole('button', { name: 'Saving…' });
    expect(savingButton).toBeDisabled();
    expect(savingButton).toHaveFocus();
    expect(serviceMocks.createSavedSearch).toHaveBeenCalledWith({
      query: 'rent',
      filters: expect.objectContaining({ source: 'youtube', date_from: '2026-01-01' }),
    });
    resolveSave?.(saved);

    expect(await screen.findByRole('alert')).toHaveTextContent('Search saved and synchronized.');
    expect(screen.getByRole('button', { name: 'Save search' })).toHaveFocus();
    expect(screen.getByText('rent')).toBeVisible();
  });

  it('prevents blank saves and reports remote save failure without a false entry', async () => {
    serviceMocks.user = { id: 'user-1' };
    serviceMocks.listFavorites.mockResolvedValue({ items: [] });
    serviceMocks.listSavedSearches.mockResolvedValue({ items: [] });
    serviceMocks.createSavedSearch.mockRejectedValue(new Error('unavailable'));
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/saved']}>
        <FavoritesPage />
      </MemoryRouter>
    );

    expect(screen.getByRole('button', { name: 'Save search' })).toBeDisabled();
    await user.type(screen.getByLabelText('Query'), 'rent');
    await user.click(screen.getByRole('button', { name: 'Save search' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The search could not be saved. Try again.'
    );
    expect(screen.getByText('No saved searches yet.')).toBeVisible();
  });

  it('reloads local moments and searches after cross-tab storage events', async () => {
    serviceMocks.reloadFavorites.mockReturnValue([
      {
        videoId: 'video-tab',
        segIndex: 5,
        startMs: 5_000,
        endMs: 7_000,
        text: 'Cross-tab moment',
      },
    ]);
    serviceMocks.reloadSavedSearches.mockReturnValue([
      {
        id: 'local:tab-search',
        query: 'cross-tab search',
        filters: {},
        created_at: '2026-08-06T00:00:00Z',
      },
    ]);

    render(
      <MemoryRouter initialEntries={['/saved']}>
        <FavoritesPage />
      </MemoryRouter>
    );

    window.dispatchEvent(new StorageEvent('storage', { key: 'favorites:v1' }));
    window.dispatchEvent(new StorageEvent('storage', { key: 'saved-searches:v1' }));

    expect(await screen.findByText('Cross-tab moment')).toBeVisible();
    expect(await screen.findByText('cross-tab search')).toBeVisible();
  });
});
