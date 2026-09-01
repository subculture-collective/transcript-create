import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SearchPage from '../routes/SearchPage';
import { api, favorites, http } from '../services';
import { renderWithProviders } from './test-utils';
import axe from 'axe-core';
import { formatDate } from '../features/archive/format';

const searchParamsMock = vi.fn();
let currentSearchParams = new URLSearchParams();
const serviceMocks = vi.hoisted(() => ({
  addFavorite: vi.fn(),
}));

const groupedResult = {
  total_moments: 1,
  total_videos: 1,
  groups: [
    {
      video: {
        id: 'video-1',
        youtube_id: 'abc123',
        title: 'VOD one',
        channel_name: 'Channel Alpha',
        duration_seconds: 1200,
        uploaded_at: '2026-05-10T00:00:00Z',
      },
      moments: [
        {
          id: 1,
          video_id: 'video-1',
          start_ms: 12000,
          end_ms: 18000,
          snippet: 'the <mark>rent</mark> is too high',
          source: 'whisper',
        },
      ],
    },
  ],
};

vi.mock('../services', async () => {
  const actual = await vi.importActual<typeof import('../services')>('../services');
  return {
    ...actual,
    apiAddFavorite: serviceMocks.addFavorite,
    track: vi.fn(),
  };
});

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useSearchParams: () => [currentSearchParams, searchParamsMock],
  };
});

describe('SearchPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    currentSearchParams = new URLSearchParams();
    serviceMocks.addFavorite.mockResolvedValue({ id: 'favorite-1' });

    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
  });

  it('ignores removed URL filters and shows grouped actions', async () => {
    currentSearchParams = new URLSearchParams({
      q: 'rent',
      source: 'youtube',
      category: 'news',
      min_duration: '120',
      max_duration: '3600',
      sort_by: 'date_desc',
      video_id: 'video-1',
      limit: '25',
      offset: '50',
    });

    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({
      suggestions: [{ term: 'gaza', frequency: 5 }],
    });
    const searchGroupedMock = vi.spyOn(api, 'searchGrouped').mockResolvedValue({
      total_moments: 1,
      total_videos: 1,
      groups: [
        {
          video: {
            id: 'video-1',
            youtube_id: 'abc123',
            title: 'VOD one',
            channel_name: 'Channel Alpha',
            duration_seconds: 1200,
            uploaded_at: '2026-05-10T00:00:00Z',
          },
          moments: [
            {
              id: 1,
              video_id: 'video-1',
              start_ms: 12000,
              end_ms: 18000,
              snippet: 'the <mark>rent</mark> is too high',
              source: 'whisper',
            },
          ],
        },
      ],
    } as never);

    const { container } = renderWithProviders(<SearchPage />);

    await waitFor(() => {
      expect(searchGroupedMock).toHaveBeenCalledWith(
        'rent',
        expect.objectContaining({
          sort_by: 'date_desc',
          video_id: 'video-1',
          match_mode: 'topic',
          limit: 20,
          offset: 0,
        }),
        expect.any(AbortSignal)
      );
    });

    expect(await screen.findByText('Play all matches')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy quote' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save moment' })).toBeInTheDocument();

    expect(screen.getByText('rent', { selector: 'mark' })).toBeInTheDocument();
    expect(screen.getByText('Channel Alpha')).toBeInTheDocument();
    expect(screen.getByText(formatDate('2026-05-10T00:00:00Z'))).toBeInTheDocument();
    expect(screen.getByText('20:00')).toBeInTheDocument();
    expect(screen.getByText('1', { selector: '.font-mono.text-3xl' })).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Open VOD one' })[0]).toHaveAttribute(
      'href',
      '/v/video-1'
    );
    expect(screen.getByRole('link', { name: 'Play all matches' })).toHaveAttribute(
      'href',
      '/v/video-1?t=12&q=rent&play=matches#moment-12000'
    );

    expect(screen.getByRole('link', { name: 'gaza' })).toHaveAttribute('href', '/search?q=gaza');
    expect(screen.queryByRole('combobox', { name: 'Transcript' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Category' })).not.toBeInTheDocument();
    expect(screen.queryByRole('spinbutton', { name: 'Minimum seconds' })).not.toBeInTheDocument();
    expect(screen.queryByRole('spinbutton', { name: 'Maximum seconds' })).not.toBeInTheDocument();
    expect((await axe.run(container)).violations).toEqual([]);
  });

  it('keeps search usable when suggested searches fail', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });

    vi.spyOn(api, 'getSearchSuggestions').mockRejectedValue(new Error('unavailable'));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const searchGroupedMock = vi.spyOn(api, 'searchGrouped').mockResolvedValue({
      total_moments: 0,
      total_videos: 0,
      groups: [],
    } as never);

    renderWithProviders(<SearchPage />);

    await waitFor(() => {
      expect(searchGroupedMock).toHaveBeenCalledWith(
        'rent',
        expect.objectContaining({
          video_id: undefined,
          match_mode: 'topic',
          limit: 20,
          offset: 0,
        }),
        expect.any(AbortSignal)
      );
    });

    expect(screen.queryByText('Suggested searches')).not.toBeInTheDocument();
  });

  it('prevents a blank query from being submitted', async () => {
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    const searchGroupedMock = vi.spyOn(api, 'searchGrouped');

    renderWithProviders(<SearchPage />);

    expect(screen.getByRole('button', { name: 'Search archive' })).toBeDisabled();
    expect(searchGroupedMock).not.toHaveBeenCalled();
  });

  it('announces transcript scanning while search results load', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockImplementation(() => new Promise(() => {}));

    renderWithProviders(<SearchPage />);

    expect(await screen.findByRole('status')).toHaveTextContent('Searching the archive…');
    expect(screen.getByText('Scanning transcripts…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Searching…' })).toBeDisabled();
  });

  it('exports and queues every matching mention', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockResolvedValue({
      total_moments: 0,
      total_videos: 0,
      groups: [],
    } as never);
    vi.spyOn(api, 'getMentionCollection').mockResolvedValue({
      items: [
        {
          video_id: 'video-1',
          video_title: 'Episode one',
          start_ms: 12000,
          end_ms: 18000,
          snippet: 'the rent is high',
          source: 'whisper',
          deep_link: '/v/video-1?t=12',
        },
      ],
    });

    renderWithProviders(<SearchPage />);
    expect(await screen.findByRole('link', { name: 'Export CSV' })).toHaveAttribute(
      'href',
      expect.stringContaining('search/mentions/export')
    );
    await userEvent.click(screen.getByRole('button', { name: 'Add every mention to queue' }));

    expect(await screen.findByText('Playback queue')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Episode one at 12s' })).toHaveAttribute(
      'href',
      '/v/video-1?t=12'
    );
    expect(screen.getByRole('status')).toHaveTextContent('1 mentions added');
  });

  it('clears the complete query and filter state', async () => {
    currentSearchParams = new URLSearchParams({
      q: 'rent',
      source: 'youtube',
      category: 'news',
      date_from: '2026-01-01',
      date_to: '2026-02-01',
      min_duration: '120',
      max_duration: '3600',
      sort_by: 'date_desc',
    });
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockResolvedValue(groupedResult as never);

    renderWithProviders(<SearchPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Clear query and dates' }));

    expect(searchParamsMock).toHaveBeenCalledOnce();
    expect(searchParamsMock.mock.calls[0]?.[0]).toEqual(new URLSearchParams());
    expect(screen.getByRole('searchbox', { name: 'Search query' })).toHaveValue('');
    expect(screen.getByRole('combobox', { name: 'Sort' })).toHaveValue('relevance');
  });

  it('renders a true no-match state after a successful empty search', async () => {
    currentSearchParams = new URLSearchParams({ q: 'no such phrase' });
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockResolvedValue({
      total_moments: 0,
      total_videos: 0,
      groups: [],
    } as never);

    renderWithProviders(<SearchPage />);

    expect(
      await screen.findByRole('heading', { name: 'No transcript matches' })
    ).toBeInTheDocument();
    expect(screen.getByText(/Try fewer words, remove the date range/)).toBeInTheDocument();
  });

  it('loads the next raw-moment page without replacing visible VOD groups', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    const searchGrouped = vi
      .spyOn(api, 'searchGrouped')
      .mockResolvedValueOnce({
        ...groupedResult,
        page_info: {
          limit: 20,
          offset: 0,
          has_next_page: true,
          has_previous_page: false,
          next_offset: 20,
        },
      } as never)
      .mockResolvedValueOnce({
        ...groupedResult,
        groups: [
          {
            ...groupedResult.groups[0],
            moments: [
              { ...groupedResult.groups[0].moments[0], id: 2, start_ms: 40_000, end_ms: 46_000 },
            ],
          },
        ],
        page_info: { limit: 20, offset: 20, has_next_page: false, has_previous_page: true },
      } as never);

    renderWithProviders(<SearchPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Load 20 more' }));

    await waitFor(() =>
      expect(searchGrouped).toHaveBeenLastCalledWith(
        'rent',
        expect.objectContaining({ limit: 20, offset: 20 }),
        expect.any(AbortSignal)
      )
    );
    expect(await screen.findByText('Showing 2 moments in 1 VODs')).toBeInTheDocument();
    expect(screen.getByText('00:00:12')).toBeInTheDocument();
  });

  it('announces clipboard success and failure for result actions', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockResolvedValue(groupedResult as never);
    const writeText = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('clipboard denied'));
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });

    renderWithProviders(<SearchPage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Copy link' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Timestamp link copied.');
    expect(writeText).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining('/v/video-1?t=12#moment-12000')
    );

    await userEvent.click(screen.getByRole('button', { name: 'Copy quote' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Quote copied.');
    expect(writeText).toHaveBeenNthCalledWith(2, expect.stringContaining('— VOD one, 00:00:12'));

    await userEvent.click(screen.getByRole('button', { name: 'Copy link' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The timestamp link could not be copied.'
    );
  });

  it('saves an anonymous result locally and identifies the saved result', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockResolvedValue(groupedResult as never);
    const toggle = vi.spyOn(favorites, 'toggle').mockImplementation(() => {});

    renderWithProviders(<SearchPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Save moment' }));

    expect(toggle).toHaveBeenCalledWith(
      expect.objectContaining({
        videoId: 'video-1',
        startMs: 12000,
        endMs: 18000,
        source: 'whisper',
      })
    );
    expect(await screen.findByRole('status')).toHaveTextContent('Moment saved.');
    expect(screen.getByRole('button', { name: 'Saved moment' })).toBeDisabled();
  });

  it('saves an authenticated result to the account', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });
    vi.mocked(http.get).mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return {
          json: vi.fn().mockResolvedValue({ user: { id: 'user-1', email: 'person@example.com' } }),
        } as never;
      }
      if (path === 'auth/csrf') {
        return { json: vi.fn().mockResolvedValue({ csrf_token: 'csrf-token' }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockResolvedValue(groupedResult as never);

    renderWithProviders(<SearchPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Save moment' }));

    expect(serviceMocks.addFavorite).toHaveBeenCalledWith({
      video_id: 'video-1',
      start_ms: 12000,
      end_ms: 18000,
      text: 'the rent is too high',
    });
    expect(await screen.findByRole('status')).toHaveTextContent('Moment saved.');
  });

  it('reports save failure without marking the result saved', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockResolvedValue(groupedResult as never);
    vi.spyOn(favorites, 'toggle').mockImplementation(() => {
      throw new Error('storage full');
    });
    vi.spyOn(console, 'error').mockImplementation(() => {});

    renderWithProviders(<SearchPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Save moment' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save this moment');
    expect(screen.getByRole('button', { name: 'Save moment' })).toBeEnabled();
    expect(screen.queryByText('Moment saved.')).not.toBeInTheDocument();
  });

  it('keeps the existing queue when queue creation fails', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });
    const existingQueue = [
      {
        video_id: 'existing-video',
        video_title: 'Existing episode',
        start_ms: 5000,
        end_ms: 9000,
        snippet: 'existing queue item',
        source: 'whisper',
        deep_link: '/v/existing-video?t=5',
      },
    ];
    vi.mocked(localStorage.getItem).mockReturnValue(JSON.stringify(existingQueue));
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockResolvedValue(groupedResult as never);
    vi.spyOn(api, 'getMentionCollection').mockRejectedValue(new Error('unavailable'));

    renderWithProviders(<SearchPage />);
    expect(await screen.findByRole('link', { name: 'Existing episode at 5s' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Add every mention to queue' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The playback queue could not be created.'
    );
    expect(screen.getByRole('link', { name: 'Existing episode at 5s' })).toBeInTheDocument();
  });

  it('announces search failure while preserving the editable query', async () => {
    currentSearchParams = new URLSearchParams({ q: 'rent' });
    vi.spyOn(api, 'getSearchSuggestions').mockResolvedValue({ suggestions: [] });
    vi.spyOn(api, 'searchGrouped').mockRejectedValue(new Error('grouped unavailable'));
    vi.spyOn(api, 'search').mockRejectedValue(new DOMException('search unavailable', 'AbortError'));

    renderWithProviders(<SearchPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Search failed. Try again.');
    const query = screen.getByRole('searchbox', { name: 'Search query' });
    expect(query).toHaveValue('rent');
    await userEvent.type(query, ' control');
    expect(query).toHaveValue('rent control');
  });
});
