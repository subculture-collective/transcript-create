import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import StreamsPage from '../routes/StreamsPage';
import { render } from '@testing-library/react';
import { api } from '../services';

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

    const renderedLinks = screen.getAllByRole('link', { name: /stream/i });
    expect(renderedLinks[0]).toHaveAttribute('href', '/v/video-1');
    expect(renderedLinks[1]).toHaveAttribute('href', '/v/video-2');
    expect(screen.getByText('First stream')).toBeInTheDocument();
    expect(screen.getByText('Channel Alpha')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'VOD metadata' })).toBeInTheDocument();
    expect(screen.getByText('Guest One')).toBeInTheDocument();
    expect(screen.getByText('Chadvice')).toBeInTheDocument();
    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 24, offset: 0, completed_only: false, date_field: 'uploaded_at' })
    );

    await user.click(screen.getByRole('button', { name: /next page/i }));

    await waitFor(() => {
      expect(listMock).toHaveBeenCalledTimes(2);
    });

    expect(listMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 24, offset: 24, completed_only: false, date_field: 'uploaded_at' })
    );
    expect(screen.getByText('Second stream')).toBeInTheDocument();
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
      <MemoryRouter
        initialEntries={[
          '/streams?q=alpha&date_from=2026-05-01&date_to=2026-05-31',
        ]}
      >
        <StreamsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(listMock).toHaveBeenCalledWith(
        expect.objectContaining({
          q: 'alpha',
          completed_only: false,
          date_field: 'uploaded_at',
          date_from: '2026-05-01',
          date_to: '2026-05-31',
        })
      );
    });

    expect(screen.getByDisplayValue('alpha')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /reset/i }));

    await waitFor(() => {
      expect(screen.getByLabelText('Search VODs')).toHaveValue('');
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
});
