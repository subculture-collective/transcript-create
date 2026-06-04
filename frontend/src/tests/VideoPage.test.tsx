import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { screen, waitFor } from '@testing-library/react';
import { AuthProvider } from '../services/auth';
import { api } from '../services';
import { http } from '../services/api';
import VideoPage from '../routes/VideoPage';
import { render } from '@testing-library/react';

vi.mock('../components/YouTubePlayer', () => ({
  __esModule: true,
  default: () => <div data-testid="youtube-player" />,
}));

describe('VideoPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders people and content tags near the VOD metadata', async () => {
    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);

    vi.spyOn(api, 'getVideo').mockResolvedValue({
      id: 'video-1',
      youtube_id: 'abc123xyz89',
      title: 'Guest Stream',
      channel_name: 'Channel Alpha',
      duration_seconds: 1800,
      uploaded_at: '2026-05-30T10:00:00Z',
      has_whisper_transcript: true,
      people: [{ slug: 'guest-one', display_name: 'Guest One', aliases: [] }],
      tags: [{ slug: 'chadvice', label: 'Chadvice', kind: 'category' }],
    } as never);

    vi.spyOn(api, 'getTranscript').mockResolvedValue({ video_id: 'video-1', segments: [] } as never);

    render(
      <MemoryRouter initialEntries={['/v/video-1']}>
        <AuthProvider>
          <Routes>
            <Route path="/v/:videoId" element={<VideoPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Guest Stream' })).toBeInTheDocument();
    });

    expect(screen.getByRole('group', { name: 'People on stream' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Content tags' })).toBeInTheDocument();
    expect(screen.getByText('Guest One')).toBeInTheDocument();
    expect(screen.getByText('Chadvice')).toBeInTheDocument();
    expect(screen.getByText('Channel Alpha')).toBeInTheDocument();
  });
});
