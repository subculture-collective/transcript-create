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

    expect(screen.getByText('First stream')).toBeInTheDocument();
    expect(screen.getByText('Channel Alpha')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText('Whisper transcript')).toBeInTheDocument();
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
    expect(screen.getByText('YouTube captions')).toBeInTheDocument();
    expect(screen.getByText('Search YouTube captions')).toBeInTheDocument();
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
          '/streams?q=alpha&completed_only=false&date_field=created_at&date_from=2026-05-01&date_to=2026-05-31',
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
          date_field: 'created_at',
          date_from: '2026-05-01',
          date_to: '2026-05-31',
        })
      );
    });

    expect(screen.getByDisplayValue('alpha')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Created date')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /reset/i }));

    await waitFor(() => {
      expect(screen.getByDisplayValue('Uploaded date')).toBeInTheDocument();
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
    expect(screen.getByText('No transcript yet')).toBeInTheDocument();
  });
});
