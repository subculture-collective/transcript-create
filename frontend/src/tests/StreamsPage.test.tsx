import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import StreamsPage from '../routes/StreamsPage';
import { render } from '@testing-library/react';
import { api } from '../services';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

describe('StreamsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders stream cards and paginates', async () => {
    const firstPage = {
      items: [
        {
          id: 'video-2',
          youtube_id: 'def456uvw12',
          title: 'Older stream',
          channel_name: 'Channel Beta',
          duration_seconds: 985,
          state: 'processing',
          caption_ingest_state: 'pending',
          diarization_state: 'queued',
          uploaded_at: '2026-05-01T12:00:00Z',
          created_at: '2026-04-30T12:00:00Z',
          updated_at: '2026-05-02T12:00:00Z',
          has_whisper_transcript: false,
          has_youtube_transcript: true,
        },
        {
          id: 'video-1',
          youtube_id: 'abc123xyz89',
          title: 'First stream',
          channel_name: 'Channel Alpha',
          duration_seconds: 3721,
          state: 'ready',
          caption_ingest_state: 'done',
          diarization_state: 'done',
          uploaded_at: '2026-05-10T12:00:00Z',
          created_at: '2026-05-09T12:00:00Z',
          updated_at: '2026-05-11T12:00:00Z',
          has_whisper_transcript: true,
          has_youtube_transcript: false,
          people: [{ slug: 'guest-one', display_name: 'Guest One', aliases: [] }],
          tags: [{ slug: 'chadvice', label: 'Chadvice', kind: 'category' }],
        },
      ],
      page_info: {
        has_next_page: true,
        has_previous_page: false,
        next_cursor: 'next-cursor',
        previous_cursor: null,
        total_count: 25,
      },
    };

    const secondPage = {
      items: [
        {
          id: 'video-2',
          youtube_id: 'def456uvw12',
          title: 'Second stream',
          channel_name: 'Channel Beta',
          duration_seconds: 985,
          state: 'processing',
          caption_ingest_state: 'pending',
          diarization_state: 'queued',
          uploaded_at: '2026-05-01T12:00:00Z',
          created_at: '2026-04-30T12:00:00Z',
          updated_at: '2026-05-02T12:00:00Z',
          has_whisper_transcript: false,
          has_youtube_transcript: true,
        },
      ],
      page_info: {
        has_next_page: false,
        has_previous_page: true,
        next_cursor: null,
        previous_cursor: 'previous-cursor',
        total_count: 25,
      },
    };

    const listMock = vi
      .spyOn(api, 'listStreamLibrary')
      .mockResolvedValueOnce(firstPage as never)
      .mockResolvedValueOnce(secondPage as never);

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/streams']}>
        <StreamsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(listMock).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getByRole('link', { name: 'Watch First stream with transcript' })
    ).toHaveAttribute('href', '/v/video-1');
    expect(screen.getByText('First stream')).toBeInTheDocument();
    expect(screen.getByText(/Guest One · Chadvice/)).toBeInTheDocument();
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        limit: 12,
        cursor: undefined,
        date_field: 'uploaded_at',
      }),
      expect.any(AbortSignal)
    );

    await user.click(screen.getByRole('button', { name: /load more/i }));

    await waitFor(() => {
      expect(listMock).toHaveBeenCalledTimes(2);
    });

    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        limit: 12,
        cursor: 'next-cursor',
        date_field: 'uploaded_at',
      }),
      undefined
    );
    expect(screen.getByText('Older stream')).toBeInTheDocument();
    expect(screen.queryByText('Second stream')).not.toBeInTheDocument();
  });

  it('submits search and filter state into the URL', async () => {
    const listMock = vi.spyOn(api, 'listStreamLibrary').mockResolvedValue({
      items: [],
      page_info: {
        has_next_page: false,
        has_previous_page: false,
        next_cursor: null,
        previous_cursor: null,
        total_count: 0,
      },
    } as never);

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/streams?q=alpha&date_from=2026-05-01&date_to=2026-05-31']}>
        <StreamsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(listMock).toHaveBeenCalledWith(
        expect.objectContaining({
          q: 'alpha',
          date_field: 'uploaded_at',
          date_from: '2026-05-01',
          date_to: '2026-05-31',
        }),
        expect.any(AbortSignal)
      );
    });

    expect(screen.getByDisplayValue('alpha')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/minimum minutes/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/maximum minutes/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/transcript source/i)).not.toBeInTheDocument();

    await user.clear(screen.getByLabelText('Search VODs'));
    await user.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => {
      expect(screen.getByLabelText('Search VODs')).toHaveValue('');
    });
  });

  it('strips retired VOD filters from the URL and never sends them', async () => {
    const listMock = vi.spyOn(api, 'listStreamLibrary').mockResolvedValue({
      items: [],
      page_info: { has_next_page: false, has_previous_page: false, total_count: 0 },
    } as never);
    render(
      <MemoryRouter
        initialEntries={[
          '/episodes?date_from=2026-01-01&min_duration=60&max_duration=120&transcript_source=youtube&source=asr',
        ]}
      >
        <StreamsPage />
        <LocationProbe />
      </MemoryRouter>
    );

    await waitFor(() => expect(listMock).toHaveBeenCalled());
    expect(listMock.mock.calls.at(-1)?.[0]).toEqual(
      expect.not.objectContaining({
        min_duration: expect.anything(),
        max_duration: expect.anything(),
        transcript_source: expect.anything(),
      })
    );
    expect(screen.getByLabelText('From')).toHaveValue('2026-01-01');
    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/episodes?date_from=2026-01-01');
    });
  });

  it('shows explicit no-transcript indicator', async () => {
    vi.spyOn(api, 'listStreamLibrary').mockResolvedValue({
      items: [
        {
          id: 'video-3',
          youtube_id: 'ghi789rst34',
          title: 'Pending stream',
          state: 'queued',
          has_whisper_transcript: false,
          has_youtube_transcript: false,
        },
      ],
      page_info: {
        has_next_page: false,
        has_previous_page: false,
        next_cursor: null,
        previous_cursor: null,
        total_count: 1,
      },
    } as never);

    render(
      <MemoryRouter initialEntries={['/streams']}>
        <StreamsPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('Pending stream')).toBeInTheDocument());
    expect(screen.queryByText('No transcript yet')).not.toBeInTheDocument();
  });

  it('reports a library failure without presenting stale results or an empty state', async () => {
    vi.spyOn(api, 'listStreamLibrary').mockRejectedValue(new Error('network unavailable'));

    render(
      <MemoryRouter initialEntries={['/episodes']}>
        <StreamsPage />
      </MemoryRouter>
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('VOD library unavailable');
    expect(screen.queryByRole('region', { name: 'latest feed' })).not.toBeInTheDocument();
    expect(screen.queryByText('No VODs match these filters.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows a stable initial skeleton while the VOD library is loading', () => {
    vi.spyOn(api, 'listStreamLibrary').mockReturnValue(new Promise(() => {}) as never);

    const { container } = render(
      <MemoryRouter initialEntries={['/episodes']}>
        <StreamsPage />
      </MemoryRouter>
    );

    expect(screen.getByRole('region', { name: 'Loading feed' })).toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(6);
  });

  it('explains how to recover from a successful no-match result', async () => {
    vi.spyOn(api, 'listStreamLibrary').mockResolvedValue({
      items: [],
      page_info: {
        has_next_page: false,
        has_previous_page: false,
        next_cursor: null,
        previous_cursor: null,
        total_count: 0,
      },
    } as never);

    render(
      <MemoryRouter initialEntries={['/episodes?q=impossible']}>
        <StreamsPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('No VODs match these filters.')).toBeInTheDocument();
    expect(screen.getByText(/Try broadening the date range/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('preserves each loaded tab while switching between discovery feeds', async () => {
    const library = vi.spyOn(api, 'listStreamLibrary').mockResolvedValue({
      items: [{ id: 'video-1', youtube_id: 'abc123xyz89', title: 'Latest stream' }],
      page_info: { has_next_page: false, has_previous_page: false, total_count: 1 },
    } as never);
    vi.spyOn(api, 'listDiscovery').mockResolvedValue({
      items: [
        {
          kind: 'topic',
          topic: {
            slug: 'labor',
            label: 'Labor',
            source: 'curated',
            total_videos: 4,
            total_moments: 12,
          },
        },
      ],
      page_info: { has_next_page: false, has_previous_page: false, total_count: 1 },
    } as never);
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/episodes']}>
        <StreamsPage />
      </MemoryRouter>
    );

    expect(await screen.findByText('Latest stream')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Topics' }));
    expect(await screen.findByText('Labor')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Latest' }));
    expect(await screen.findByText('Latest stream')).toBeInTheDocument();
    expect(library).toHaveBeenCalledTimes(1);
  });
});
