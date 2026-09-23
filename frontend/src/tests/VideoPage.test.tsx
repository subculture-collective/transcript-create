import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { AuthProvider } from '../services/auth';
import { api, favorites } from '../services';
import { http } from '../services/api';
import VideoPage from '../routes/VideoPage';
import { render } from '@testing-library/react';
import axe from 'axe-core';

const playerMocks = vi.hoisted(() => ({
  destroy: vi.fn(),
  previewRange: vi.fn(),
  pause: vi.fn(),
  getCurrentTime: vi.fn(() => 0),
  seekTo: vi.fn(),
  togglePlay: vi.fn(),
}));

const serviceMocks = vi.hoisted(() => ({
  addFavorite: vi.fn(),
  deleteFavorite: vi.fn(),
  listFavorites: vi.fn(),
}));

vi.mock('../components/YouTubePlayer', async () => {
  const React = await vi.importActual<typeof import('react')>('react');
  return {
    __esModule: true,
    default: React.forwardRef((_props, ref) => {
      React.useImperativeHandle(ref, () => playerMocks);
      return <div data-testid="youtube-player" />;
    }),
  };
});

vi.mock('../services', async () => {
  const actual = await vi.importActual<typeof import('../services')>('../services');
  return {
    ...actual,
    apiAddFavorite: serviceMocks.addFavorite,
    apiDeleteFavorite: serviceMocks.deleteFavorite,
    apiListFavorites: serviceMocks.listFavorites,
    track: vi.fn(),
  };
});

const defaultVideo = {
  id: 'video-1',
  youtube_id: 'abc123xyz89',
  title: 'Test episode',
  has_whisper_transcript: true,
};

const defaultTranscript = {
  video_id: 'video-1',
  segments: [
    { start_ms: 12_000, end_ms: 18_000, text: 'First sentence. Second sentence.' },
    { start_ms: 18_000, end_ms: 24_000, text: 'Another thought.' },
  ],
};

function mockAuth(user: object | null = null) {
  vi.spyOn(http, 'get').mockImplementation(((path: string) => {
    if (path === 'auth/me') {
      return { json: vi.fn().mockResolvedValue({ user, capabilities: [] }) } as never;
    }
    return { json: vi.fn().mockResolvedValue({}) } as never;
  }) as never);
}

function mockEpisode(transcript: object = defaultTranscript, chapters: object[] = []) {
  vi.spyOn(api, 'getVideo').mockResolvedValue(defaultVideo as never);
  vi.spyOn(api, 'getTranscript').mockResolvedValue(transcript as never);
  vi.spyOn(api, 'getVideoChapters').mockResolvedValue({ chapters } as never);
}

function renderVideo(entry = '/v/video-1') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AuthProvider>
        <Routes>
          <Route path="/v/:videoId" element={<VideoPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe('VideoPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    window.location.hash = '';
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
    serviceMocks.listFavorites.mockResolvedValue({ items: [] });
    serviceMocks.addFavorite.mockResolvedValue({ id: 'favorite-1' });
    serviceMocks.deleteFavorite.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('opens a shared passage in a fresh session and preserves its exact range', async () => {
    mockAuth();
    mockEpisode();
    renderVideo('/v/video-1?t=12&t_ms=12125&end_ms=22000');
    expect(await screen.findByRole('heading', { name: 'Share a passage' })).toBeInTheDocument();
    expect(screen.getByLabelText('Start time')).toHaveValue('00:00:12.125');
    expect(screen.getByLabelText('End time')).toHaveValue('00:00:22');
    fireEvent.click(screen.getByRole('button', { name: 'Preview passage' }));
    expect(playerMocks.previewRange).toHaveBeenCalledWith(12.125, 22);
    fireEvent.click(screen.getByRole('button', { name: 'Close passage' }));
    expect(screen.queryByRole('heading', { name: 'Share a passage' })).not.toBeInTheDocument();
  });

  it('starts a passage from a transcript selection and leaves old links start-only', async () => {
    mockAuth();
    mockEpisode();
    renderVideo('/v/video-1?t=12');
    fireEvent.click(await screen.findByRole('button', { name: 'Open paragraph at 00:00:12' }));
    expect(screen.queryByLabelText('End time')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Share passage' }));
    expect(await screen.findByLabelText('Start time')).toHaveValue('00:00:12');
    expect(screen.getByLabelText('End time')).toHaveValue('00:00:18');
    fireEvent.click(screen.getByRole('button', { name: 'Open paragraph at 00:00:18' }));
    fireEvent.click(screen.getByRole('button', { name: /^Play from here/ }));
    expect(screen.queryByLabelText('End time')).not.toBeInTheDocument();
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

    const { container } = render(
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

    await waitFor(() => expect(document.title).toBe('Guest Stream | Transcript Archive'));
    expect(screen.getByText(/Automated transcripts can contain errors/i)).toBeInTheDocument();
    expect(
      screen.getByText(/verify quotations against the linked source video/i)
    ).toBeInTheDocument();

    expect(screen.getByRole('group', { name: 'People on stream' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Content tags' })).toBeInTheDocument();
    expect(screen.getByText('Guest One')).toBeInTheDocument();
    expect(screen.getByText('Chadvice')).toBeInTheDocument();
    expect(screen.getByText('Channel Alpha')).toBeInTheDocument();

    fireEvent.scroll(window);
    expect(await screen.findByRole('button', { name: 'Enable follow live' })).toBeInTheDocument();
    expect((await axe.run(container)).violations).toEqual([]);
  });

  it('shows a retry action when the transcript request fails', async () => {
    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getVideo').mockResolvedValue({
      id: 'video-1',
      youtube_id: 'abc123xyz89',
      title: 'Slow episode',
      has_whisper_transcript: true,
    } as never);
    vi.spyOn(api, 'getTranscript').mockRejectedValue(new Error('timeout'));

    render(
      <MemoryRouter initialEntries={['/v/video-1']}>
        <AuthProvider>
          <Routes>
            <Route path="/v/:videoId" element={<VideoPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    expect(
      await screen.findByRole('heading', { name: 'Transcript took too long to load' })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(api.getTranscript).toHaveBeenCalledWith('video-1', 'whisper');
  });

  it('provides an accessible three-position mobile transcript sheet', async () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
    mockAuth();
    mockEpisode();
    renderVideo();

    const sheet = await screen.findByLabelText('half episode reader');
    expect(sheet).toHaveAttribute('aria-expanded', 'false');
    fireEvent.keyDown(screen.getByRole('button', { name: /half transcript sheet/i }), {
      key: 'ArrowUp',
    });
    expect(await screen.findByLabelText('expanded episode reader')).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(await screen.findByLabelText('collapsed episode reader')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Chapters' })).toBeInTheDocument();
  });

  it('accepts the transcript source named by a legacy moment URL', async () => {
    mockAuth();
    mockEpisode({ video_id: 'video-1', source: 'youtube', segments: [] });
    window.location.hash = '#moment-youtube-12000';

    renderVideo('/v/video-1?t=12#moment-youtube-12000');

    await waitFor(() => expect(api.getTranscript).toHaveBeenCalledWith('video-1', 'youtube'));
  });

  it('distinguishes a missing video from a temporary transcript failure', async () => {
    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getVideo').mockRejectedValue({ response: { status: 404 } });
    vi.spyOn(api, 'getVideoChapters').mockResolvedValue({ chapters: [] } as never);

    render(
      <MemoryRouter initialEntries={['/v/missing']}>
        <AuthProvider>
          <Routes>
            <Route path="/v/:videoId" element={<VideoPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    expect(
      await screen.findByRole('heading', { name: 'This video is not in the archive' })
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Browse episodes' })).toHaveAttribute(
      'href',
      '/episodes'
    );
  });

  it('announces anonymous save and remove actions accurately', async () => {
    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getVideo').mockResolvedValue({
      id: 'video-toggle-save',
      youtube_id: 'abc123xyz89',
      title: 'Saveable episode',
      has_whisper_transcript: true,
    } as never);
    vi.spyOn(api, 'getTranscript').mockResolvedValue({
      video_id: 'video-toggle-save',
      segments: [{ start_ms: 12_000, end_ms: 18_000, text: 'A moment worth saving.' }],
    } as never);
    vi.spyOn(api, 'getVideoChapters').mockResolvedValue({ chapters: [] } as never);

    render(
      <MemoryRouter initialEntries={['/v/video-toggle-save']}>
        <AuthProvider>
          <Routes>
            <Route path="/v/:videoId" element={<VideoPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    const sentence = await screen.findByRole('button', {
      name: 'Open paragraph at 00:00:12',
    });
    fireEvent.click(sentence);
    fireEvent.click(screen.getByRole('button', { name: 'Save moment' }));
    expect(await screen.findByText('Transcript moment saved.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Remove moment' }));
    expect(await screen.findByText('Transcript moment removed.')).toBeInTheDocument();
  });

  it('opens a paragraph, plays from it on request, and resumes auto-follow', async () => {
    mockAuth();
    mockEpisode();
    const replaceState = vi.spyOn(history, 'replaceState');

    renderVideo();
    const paragraph = await screen.findByRole('button', { name: 'Open paragraph at 00:00:12' });
    fireEvent.click(paragraph);
    expect(paragraph).toHaveAttribute('aria-expanded', 'true');
    expect(playerMocks.seekTo).not.toHaveBeenCalled();
    expect(screen.getByRole('toolbar', { name: 'Passage actions' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Play from here/ }));

    expect(playerMocks.seekTo).toHaveBeenCalledWith(12, { play: true });
    expect(replaceState).toHaveBeenCalledWith(null, '', '#seg-1');

    fireEvent.keyDown(window, { key: 'PageDown' });
    const resume = await screen.findByRole('button', { name: 'Enable follow live' });
    fireEvent.click(resume);
    expect(screen.getByRole('status')).toHaveTextContent('Following live transcript');
  });

  it('honors sentence and block hashes before the rounded timestamp', async () => {
    mockAuth();
    mockEpisode({
      ...defaultTranscript,
      blocks: [
        {
          block_index: 7,
          start_ms: 12_000,
          end_ms: 24_000,
          text: 'First sentence. Second sentence. Another thought.',
          segment_ids: [0, 1],
          speaker_label: 'Hasan',
        },
      ],
    });
    window.location.hash = '#seg-1-s-1';
    const replaceState = vi.spyOn(history, 'replaceState');

    renderVideo('/v/video-1?t=18');

    const sentence = (await screen.findByText('Second sentence.')).closest('[role="button"]');
    expect(sentence).not.toBeNull();
    await waitFor(() => expect(sentence).toHaveClass('transcript-sentence-active'));
    expect(document.querySelector('#block-7')).toHaveAttribute('data-active', 'true');
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    fireEvent.click(sentence!);
    expect(playerMocks.seekTo).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /^Play from here/ }));
    expect(playerMocks.seekTo).toHaveBeenLastCalledWith(14, { play: true });
    expect(replaceState).toHaveBeenLastCalledWith(null, '', '#seg-1-s-1');
  });

  it('opens and highlights a formatted transcript block from its block hash', async () => {
    mockAuth();
    mockEpisode({
      ...defaultTranscript,
      blocks: [
        {
          block_index: 7,
          start_ms: 12_000,
          end_ms: 24_000,
          text: 'First sentence. Second sentence. Another thought.',
          segment_ids: [0, 1],
        },
      ],
    });
    window.location.hash = '#block-7';

    renderVideo();

    await waitFor(() =>
      expect(document.querySelector('#block-7')).toHaveAttribute('data-active', 'true')
    );
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it('supports split, watch, and reader layouts with reader playback control', async () => {
    mockAuth();
    mockEpisode();
    renderVideo();

    const read = await screen.findByRole('button', { name: 'Read' });
    fireEvent.click(read);
    fireEvent.click(screen.getByRole('button', { name: 'Toggle playback' }));
    expect(playerMocks.togglePlay).toHaveBeenCalledOnce();

    fireEvent.click(screen.getAllByRole('button', { name: 'Watch' })[0]);
    expect(screen.getByTestId('youtube-player')).toBeVisible();
    fireEvent.click(screen.getAllByRole('button', { name: 'Split' })[0]);
    expect(screen.getByRole('button', { name: 'Split' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('loads the transcript progressively and navigates chapter evidence', async () => {
    mockAuth();
    let resolveTranscript: (value: object) => void = () => undefined;
    vi.spyOn(api, 'getVideo').mockResolvedValue(defaultVideo as never);
    vi.spyOn(api, 'getTranscript').mockReturnValue(
      new Promise((resolve) => {
        resolveTranscript = resolve;
      }) as never
    );
    vi.spyOn(api, 'getVideoChapters').mockResolvedValue({
      chapters: [
        {
          chapter_index: 0,
          start_ms: 12_000,
          end_ms: 24_000,
          title: 'Opening argument',
          summary: 'The opening claim.',
          confidence_score: 0.9,
          status: 'ready',
          source: 'transcript',
          evidence: [{ block_index: 7, start_ms: 12_000, end_ms: 24_000, text: 'First sentence.' }],
        },
      ],
    } as never);

    renderVideo();
    expect(
      (await screen.findByText(/Loading transcript/)).closest('[role="status"]')
    ).toHaveTextContent('Loading transcript');
    await act(async () => {
      resolveTranscript({
        ...defaultTranscript,
        blocks: [
          {
            block_index: 7,
            start_ms: 12_000,
            end_ms: 24_000,
            text: 'First sentence. Second sentence. Another thought.',
            segment_ids: [0, 1],
          },
        ],
      });
    });

    fireEvent.click(await screen.findByRole('button', { name: /Opening argument/ }));
    expect(playerMocks.seekTo).toHaveBeenCalledWith(12, { play: true });
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
    expect(screen.getByRole('heading', { name: 'Opening argument' })).toBeInTheDocument();
  });

  it('searches the current VOD, wraps match navigation, and clears the query', async () => {
    mockAuth();
    mockEpisode();
    vi.spyOn(api, 'search').mockResolvedValue({
      hits: [
        { video_id: 'video-1', start_ms: 12_000, snippet: 'First match', highlights: [] },
        { video_id: 'video-1', start_ms: 18_000, snippet: 'Second match', highlights: [] },
      ],
    } as never);
    renderVideo();

    const input = await screen.findByRole('searchbox', { name: 'Search inside this VOD' });
    fireEvent.change(input, { target: { value: 'argument' } });
    fireEvent.submit(input.closest('form')!);
    await waitFor(() =>
      expect(api.search).toHaveBeenCalledWith('argument', { video_id: 'video-1' })
    );
    expect(await screen.findByText('1 / 2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Go to previous match' }));
    expect(playerMocks.seekTo).toHaveBeenLastCalledWith(18, { play: true });
    fireEvent.click(screen.getByRole('button', { name: 'Go to next match' }));
    expect(playerMocks.seekTo).toHaveBeenLastCalledWith(12, { play: true });

    fireEvent.change(input, { target: { value: '' } });
    fireEvent.submit(input.closest('form')!);
    await waitFor(() => expect(screen.queryByText('1 / 2')).not.toBeInTheDocument());
  });

  it('plays matching moments sequentially and stops after the final match', async () => {
    mockAuth();
    mockEpisode();
    vi.spyOn(api, 'search').mockResolvedValue({
      hits: [
        { video_id: 'video-1', start_ms: 12_000, snippet: 'First match', highlights: [] },
        { video_id: 'video-1', start_ms: 18_000, snippet: 'Second match', highlights: [] },
      ],
    } as never);
    renderVideo('/v/video-1?q=argument');

    const play = await screen.findByRole('button', {
      name: 'Play all matching transcript moments',
    });
    vi.useFakeTimers();
    fireEvent.click(play);
    expect(play).toHaveTextContent('Stop');
    fireEvent.click(play);
    expect(play).toHaveTextContent('Play matches');
    fireEvent.click(play);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7_000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7_000);
    });
    expect(play).toHaveTextContent('Play matches');
    expect(playerMocks.seekTo).toHaveBeenCalledWith(18, { play: true });
  });

  it('saves and removes authenticated transcript moments on the server', async () => {
    mockAuth({ id: 'user-1', email: 'reader@example.com', display_name: 'Reader' });
    mockEpisode();
    renderVideo();

    fireEvent.click(await screen.findByRole('button', { name: 'Open paragraph at 00:00:12' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save moment' }));
    await waitFor(() =>
      expect(serviceMocks.addFavorite).toHaveBeenCalledWith({
        video_id: 'video-1',
        start_ms: 12_000,
        end_ms: 18_000,
        text: 'First sentence. Second sentence.',
      })
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Remove moment' }));
    await waitFor(() => expect(serviceMocks.deleteFavorite).toHaveBeenCalledWith('favorite-1'));
    expect(await screen.findByText('Transcript moment removed.')).toBeInTheDocument();
  });

  it('announces save and clipboard failures while copying a cited quote on success', async () => {
    mockAuth();
    mockEpisode();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const toggle = vi.spyOn(favorites, 'toggle').mockImplementation(() => {
      throw new Error('storage unavailable');
    });
    const writeText = vi.mocked(navigator.clipboard.writeText);
    writeText.mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('denied'));
    renderVideo();

    fireEvent.click(await screen.findByRole('button', { name: 'Open paragraph at 00:00:12' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save moment' }));
    expect(
      await screen.findByText('The transcript moment could not be saved.')
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save moment' })).toBeInTheDocument();
    toggle.mockRestore();

    fireEvent.click(screen.getByRole('button', { name: 'Copy quote' }));
    expect(await screen.findByText('Quote copied.')).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(
      expect.stringContaining('“First sentence. Second sentence.”\n\n— Test episode, 00:00:12')
    );
    fireEvent.click(screen.getByRole('button', { name: 'Copy quote' }));
    expect(await screen.findByText('The quote could not be copied.')).toBeInTheDocument();
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

    await waitFor(() => expect(document.getElementById('moment-5956000')).not.toBeNull());
    const citedMoment = document.getElementById('moment-5956000');
    expect(citedMoment?.parentElement).toHaveTextContent('The cited sentence.');
    expect(document.querySelectorAll('#moment-5956000')).toHaveLength(1);
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  });

  it('mounts a progressive chapter from an exact canonical moment after a transcript gap', async () => {
    mockAuth();
    const segments = Array.from({ length: 600 }, (_, index) => ({
      start_ms: index * 10_000 + 140,
      end_ms: index * 10_000 + 3_140,
      text: `Sentence ${index + 1}.`,
    }));
    const target = segments[500];
    mockEpisode({ video_id: 'video-1', source: 'whisper', segments });
    window.location.hash = `#moment-whisper-${target.start_ms}`;

    renderVideo(`/v/video-1?t=${Math.floor(target.start_ms / 1000)}&source=whisper`);

    await waitFor(
      () => expect(document.getElementById(`moment-${target.start_ms}`)).not.toBeNull(),
      { timeout: 5000 }
    );
    expect(screen.getByText(/Section 6 of 7/)).toBeInTheDocument();
    expect(document.getElementById('moment-140')).toBeNull();
  });

  it('mounts a source-neutral saved moment using its exact millisecond timestamp', async () => {
    mockAuth();
    const segments = Array.from({ length: 600 }, (_, index) => ({
      start_ms: index * 10_000 + 140,
      end_ms: index * 10_000 + 3_140,
      text: `Sentence ${index + 1}.`,
    }));
    const target = segments[500];
    mockEpisode({ video_id: 'video-1', source: 'whisper', segments });

    renderVideo(`/v/video-1?t=${Math.floor(target.start_ms / 1000)}&t_ms=${target.start_ms}`);

    await waitFor(
      () => expect(document.getElementById(`moment-${target.start_ms}`)).not.toBeNull(),
      { timeout: 5000 }
    );
    expect(screen.getByText(/Section 6 of 7/)).toBeInTheDocument();
  });

  it('recovers a legacy database-id fragment from its floored timestamp', async () => {
    mockAuth();
    const segments = Array.from({ length: 600 }, (_, index) => ({
      start_ms: index * 10_000 + 140,
      end_ms: index * 10_000 + 3_140,
      text: `Sentence ${index + 1}.`,
    }));
    const target = segments[500];
    mockEpisode({ video_id: 'video-1', source: 'whisper', segments });
    window.location.hash = '#seg-4864024';

    renderVideo(`/v/video-1?t=${Math.floor(target.start_ms / 1000)}`);

    await waitFor(
      () => expect(document.getElementById(`moment-${target.start_ms}`)).not.toBeNull(),
      { timeout: 5000 }
    );
    expect(screen.getByText(/Section 6 of 7/)).toBeInTheDocument();
  });

  it('progressively mounts transcript chapters and offers a full-document escape hatch', async () => {
    mockAuth();
    const longTranscript = {
      video_id: 'video-1',
      segments: Array.from({ length: 2_700 }, (_, index) => ({
        start_ms: index * 10_000,
        end_ms: (index + 1) * 10_000,
        text: `Sentence ${index + 1}.`,
      })),
    };
    mockEpisode(longTranscript);
    window.location.hash = '#seg-251';
    renderVideo('/v/video-1?t=2500');

    await waitFor(() => expect(document.getElementById('seg-251')).not.toBeNull(), {
      timeout: 5_000,
    });
    expect(screen.getByText(/Section 3 of 30/)).toBeInTheDocument();
    expect(document.querySelectorAll('[data-transcript-sentence="true"]')).toHaveLength(270);
    expect(document.querySelectorAll('*').length).toBeLessThanOrEqual(1_500);
    expect(document.getElementById('seg-1')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Load full transcript' }));
    await waitFor(
      () =>
        expect(document.querySelectorAll('[data-transcript-sentence="true"]')).toHaveLength(2_700),
      { timeout: 5_000 }
    );
    expect(screen.getByRole('button', { name: 'Use progressive transcript' })).toBeInTheDocument();
  }, 30_000);
});
