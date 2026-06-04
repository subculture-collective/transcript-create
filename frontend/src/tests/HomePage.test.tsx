import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import HomePage from '../routes/HomePage';
import { renderWithProviders } from './test-utils';
import { api } from '../services';
import { http } from '../services/api';

describe('HomePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders archive hero and summary content', async () => {
    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getArchiveSummary').mockResolvedValue({
      creator_name: 'HasAnAra',
      video_count: 12,
      total_duration_seconds: 7260,
      transcript_word_count: 4200,
      updated_at: '2026-05-31T12:00:00Z',
      recent_videos: [
        {
          id: 'video-1',
          youtube_id: 'abc123xyz89',
          title: 'Newest VOD',
          channel_name: 'Channel Alpha',
          duration_seconds: 1800,
          uploaded_at: '2026-05-30T10:00:00Z',
          has_whisper_transcript: true,
        },
      ],
      popular_searches: [{ term: 'rent', frequency: 9 }],
    } as never);

    const user = userEvent.setup();
    renderWithProviders(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText('Search the HasanAbi broadcast archive.')).toBeInTheDocument();
    });

    expect(screen.getByPlaceholderText('Search any topic, line, guest, or phrase…')).toBeInTheDocument();
    expect(screen.getByText('VODs')).toBeInTheDocument();
    expect(screen.getByText('Newest VOD')).toBeInTheDocument();
    expect(screen.getByText('rent')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue with Google' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue with Twitch' })).toBeInTheDocument();

    const input = screen.getByPlaceholderText('Search any topic, line, guest, or phrase…');
    await user.type(input, 'archive');
    await user.click(screen.getByRole('button', { name: 'Search archive' }));
    expect(input).toHaveValue('archive');
  });
});
