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

    vi.spyOn(api, 'getTranscript').mockResolvedValue({
      video_id: 'video-1',
      segments: [],
    } as never);

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

    expect(document.title).toBe('Guest Stream | HasanAra');
    expect(screen.getByText(/Automated transcripts can contain errors/i)).toBeInTheDocument();
    expect(
      screen.getByText(/verify quotations against the linked source video/i)
    ).toBeInTheDocument();

    expect(screen.getByRole('group', { name: 'People on stream' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Content tags' })).toBeInTheDocument();
    expect(screen.getByText('Guest One')).toBeInTheDocument();
    expect(screen.getByText('Chadvice')).toBeInTheDocument();
    expect(screen.getByText('Channel Alpha')).toBeInTheDocument();
  });

  it('mounts and scrolls the canonical cited moment after transcript hydration', async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    window.location.hash = '#moment-whisper-5956000';

    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getVideo').mockResolvedValue({
      id: 'video-1',
      youtube_id: 'abc123xyz89',
      title: 'Housing stream',
      duration_seconds: 7200,
      has_whisper_transcript: true,
    } as never);
    vi.spyOn(api, 'getTranscript').mockResolvedValue({
      video_id: 'video-1',
      source: 'whisper',
      segments: [
        {
          start_ms: 5_956_000,
          end_ms: 5_960_000,
          text: 'The cited sentence. A second sentence.',
        },
      ],
      blocks: [
        {
          block_index: 0,
          start_ms: 5_956_000,
          end_ms: 5_960_000,
          text: 'The cited sentence. A second sentence.',
          segment_ids: [0],
          kind: 'paragraph',
        },
      ],
    } as never);
    vi.spyOn(api, 'getVideoChapters').mockResolvedValue({ chapters: [] } as never);

    render(
      <MemoryRouter initialEntries={['/v/video-1?t=5956&source=whisper']}>
        <AuthProvider>
          <Routes>
            <Route path="/v/:videoId" element={<VideoPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => expect(document.getElementById('moment-whisper-5956000')).not.toBeNull());
    const citedMoment = document.getElementById('moment-whisper-5956000');
    expect(citedMoment?.parentElement).toHaveTextContent('The cited sentence.');
    expect(document.querySelectorAll('#moment-whisper-5956000')).toHaveLength(1);
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  });
});
