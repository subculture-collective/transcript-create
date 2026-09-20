import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import YouTubePlayer from '../components/YouTubePlayer';
import { createRef } from 'react';
import type { YouTubePlayerHandle } from '../components/YouTubePlayer';
import { resetYouTubeApiForTests } from '../services/youtubeApi';

describe('YouTubePlayer', () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let mockPlayer: any;
  let playerState = 2;

  beforeEach(() => {
    vi.clearAllMocks();
    resetYouTubeApiForTests();
    playerState = 2;

    // Mock YouTube IFrame API
    mockPlayer = {
      seekTo: vi.fn(),
      loadVideoById: vi.fn(),
      playVideo: vi.fn(),
      pauseVideo: vi.fn(),
      getPlayerState: vi.fn(() => playerState),
      destroy: vi.fn(),
    };

    window.YT = {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      Player: vi.fn(function (this: any, _element: any, config: any) {
        this.seekTo = mockPlayer.seekTo;
        this.loadVideoById = mockPlayer.loadVideoById;
        this.playVideo = mockPlayer.playVideo;
        this.pauseVideo = mockPlayer.pauseVideo;
        this.getPlayerState = mockPlayer.getPlayerState;
        this.destroy = mockPlayer.destroy;
        // Simulate onReady callback
        setTimeout(() => config.events.onReady(), 0);
        return this;
      }),
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
  });

  afterEach(() => {
    delete window.YT;
    resetYouTubeApiForTests();
    document.querySelector('script[data-youtube-iframe-api]')?.remove();
  });

  it('previews a bounded range and resumes unrestricted playback with a seek', async () => {
    const ref = createRef<YouTubePlayerHandle>();
    render(<YouTubePlayer ref={ref} videoId="test-video-id" />);
    await waitFor(() => expect(screen.queryByText('Loading player…')).not.toBeInTheDocument());
    ref.current?.previewRange(12.125, 24.5);
    expect(mockPlayer.loadVideoById).toHaveBeenCalledWith({
      videoId: 'test-video-id',
      startSeconds: 12.125,
      endSeconds: 24.5,
    });
    ref.current?.seekTo(24.5, { play: true });
    expect(mockPlayer.seekTo).toHaveBeenCalledWith(24.5, true);
    ref.current?.previewRange(30, 20);
    expect(mockPlayer.loadVideoById).toHaveBeenCalledTimes(1);
  });

  it('queues a bounded preview until the player is ready', async () => {
    let signalReady: (() => void) | undefined;
    window.YT!.Player = vi.fn(function (
      _element: HTMLElement,
      config: { events: { onReady: () => void } }
    ) {
      signalReady = config.events.onReady;
      return mockPlayer;
    }) as unknown as NonNullable<typeof window.YT>['Player'];
    const ref = createRef<YouTubePlayerHandle>();
    render(<YouTubePlayer ref={ref} videoId="test-video-id" start={10} />);
    await waitFor(() => expect(window.YT!.Player).toHaveBeenCalled());
    ref.current?.previewRange(12.125, 24.5);
    expect(mockPlayer.loadVideoById).not.toHaveBeenCalled();
    signalReady?.();
    await waitFor(() =>
      expect(mockPlayer.loadVideoById).toHaveBeenCalledWith({
        videoId: 'test-video-id',
        startSeconds: 12.125,
        endSeconds: 24.5,
      })
    );
    expect(mockPlayer.seekTo).not.toHaveBeenCalled();
  });

  it('renders player container', () => {
    render(<YouTubePlayer videoId="test-video-id" />);
    expect(screen.getByTitle('YouTube player')).toBeInTheDocument();
  });

  it('renders with custom title', () => {
    render(<YouTubePlayer videoId="test-video-id" title="Custom Title" />);
    expect(screen.getByTitle('Custom Title')).toBeInTheDocument();
  });

  it('initializes YouTube player with correct config', async () => {
    render(<YouTubePlayer videoId="test-video-id" start={30} />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const call = (window.YT!.Player as any).mock.calls[0];
    const config = call[1];

    expect(config.videoId).toBe('test-video-id');
    expect(config.height).toBe('100%');
    expect(config.width).toBe('100%');
    expect(config.playerVars.start).toBe(30);
    expect(config.playerVars.autoplay).toBe(0);
  });

  it('seeks to start time when ready', async () => {
    render(<YouTubePlayer videoId="test-video-id" start={45} />);

    await waitFor(() => {
      expect(mockPlayer.seekTo).toHaveBeenCalledWith(45, true);
    });
  });

  it('does not seek when start is 0', async () => {
    render(<YouTubePlayer videoId="test-video-id" start={0} />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    // Wait a bit to ensure seekTo is not called
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(mockPlayer.seekTo).not.toHaveBeenCalled();
  });

  it('exposes seekTo method via ref', async () => {
    const ref = createRef<YouTubePlayerHandle>();
    render(<YouTubePlayer ref={ref} videoId="test-video-id" />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    // Call seekTo via ref
    ref.current?.seekTo(120);

    await waitFor(() => expect(mockPlayer.seekTo).toHaveBeenCalledWith(120, true));
  });

  it('preserves a ref seek issued before the player becomes ready', async () => {
    let signalReady: (() => void) | undefined;
    window.YT!.Player = vi.fn(function (
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      this: any,
      _element: HTMLElement,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      config: any
    ) {
      this.seekTo = mockPlayer.seekTo;
      this.playVideo = mockPlayer.playVideo;
      this.getPlayerState = mockPlayer.getPlayerState;
      signalReady = config.events.onReady;
      return this;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    }) as any;

    const ref = createRef<YouTubePlayerHandle>();
    render(<YouTubePlayer ref={ref} videoId="test-video-id" />);
    await waitFor(() => expect(window.YT!.Player).toHaveBeenCalled());

    ref.current?.seekTo(120, { play: true });
    expect(mockPlayer.seekTo).not.toHaveBeenCalled();
    signalReady?.();

    await waitFor(() => {
      expect(mockPlayer.seekTo).toHaveBeenCalledWith(120, true);
      expect(mockPlayer.playVideo).toHaveBeenCalled();
    });
  });

  it('can seek and play via ref', async () => {
    const ref = createRef<YouTubePlayerHandle>();
    render(<YouTubePlayer ref={ref} videoId="test-video-id" />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    ref.current?.seekTo(120, { play: true });

    await waitFor(() => {
      expect(mockPlayer.seekTo).toHaveBeenCalledWith(120, true);
      expect(mockPlayer.playVideo).toHaveBeenCalled();
    });
  });

  it('exposes play, pause, and togglePlay methods via ref', async () => {
    const ref = createRef<YouTubePlayerHandle>();
    render(<YouTubePlayer ref={ref} videoId="test-video-id" />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    ref.current?.play();
    expect(mockPlayer.playVideo).toHaveBeenCalled();

    ref.current?.pause();
    expect(mockPlayer.pauseVideo).toHaveBeenCalled();

    ref.current?.togglePlay();
    expect(mockPlayer.playVideo).toHaveBeenCalledTimes(2);

    playerState = 1;
    ref.current?.togglePlay();
    expect(mockPlayer.pauseVideo).toHaveBeenCalledTimes(2);
  });

  it('does not call playVideo when already playing', async () => {
    mockPlayer.getPlayerState = vi.fn(() => 1);
    const ref = createRef<YouTubePlayerHandle>();
    render(<YouTubePlayer ref={ref} videoId="test-video-id" />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    ref.current?.seekTo(120, { play: true });

    await waitFor(() => expect(mockPlayer.seekTo).toHaveBeenCalledWith(120, true));
    expect(mockPlayer.playVideo).not.toHaveBeenCalled();
  });

  it('does not recreate player when start prop changes', async () => {
    const { rerender } = render(<YouTubePlayer videoId="test-video-id" start={30} />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalledTimes(1);
    });

    rerender(<YouTubePlayer videoId="test-video-id" start={90} />);

    expect(window.YT!.Player).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mockPlayer.seekTo).toHaveBeenCalledWith(90, true));
  });

  it('resets readiness and pending seek for a new video', async () => {
    const { rerender } = render(<YouTubePlayer videoId="video-one" start={30} />);
    await waitFor(() => expect(window.YT!.Player).toHaveBeenCalledTimes(1));

    rerender(<YouTubePlayer videoId="video-two" start={75} />);
    await waitFor(() => expect(window.YT!.Player).toHaveBeenCalledTimes(2));
    const secondConfig = (window.YT!.Player as ReturnType<typeof vi.fn>).mock.calls[1][1];
    expect(secondConfig.videoId).toBe('video-two');
    expect(secondConfig.playerVars.start).toBe(75);
  });

  it('handles seekTo errors gracefully', async () => {
    mockPlayer.seekTo = vi.fn(() => {
      throw new Error('Player not ready');
    });

    const ref = createRef<YouTubePlayerHandle>();
    render(<YouTubePlayer ref={ref} videoId="test-video-id" />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    // Should not throw
    expect(() => ref.current?.seekTo(120)).not.toThrow();
  });

  it('cleans up player on unmount', async () => {
    const { unmount } = render(<YouTubePlayer videoId="test-video-id" />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    unmount();

    expect(mockPlayer.destroy).toHaveBeenCalled();
  });

  it('handles destroy errors gracefully', async () => {
    mockPlayer.destroy = vi.fn(() => {
      throw new Error('Destroy error');
    });

    const { unmount } = render(<YouTubePlayer videoId="test-video-id" />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    // Should not throw
    expect(() => unmount()).not.toThrow();
  });

  it('loads the YouTube API script and initializes after its ready callback', async () => {
    const playerConstructor = window.YT!.Player;
    delete window.YT;
    const appendChildSpy = vi
      .spyOn(document.body, 'appendChild')
      .mockImplementation((node) => node);

    render(<YouTubePlayer videoId="test-video-id" />);

    await waitFor(() => {
      expect(appendChildSpy).toHaveBeenCalled();
    });

    const scriptTag = appendChildSpy.mock.calls.find(
      ([element]) => (element as HTMLElement).tagName === 'SCRIPT'
    )?.[0] as HTMLScriptElement;
    expect(scriptTag.src).toBe('https://www.youtube.com/iframe_api');
    expect(scriptTag.dataset.youtubeIframeApi).toBe('true');

    window.YT = { Player: playerConstructor };
    window.onYouTubeIframeAPIReady?.();
    await waitFor(() => expect(playerConstructor).toHaveBeenCalled());

    appendChildSpy.mockRestore();
  });

  it('does not reload API script when already available', async () => {
    // YT is already available from beforeEach
    const appendChildSpy = vi.spyOn(document.body, 'appendChild');

    render(<YouTubePlayer videoId="test-video-id" />);

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled();
    });

    // Check if appendChild was called with a script tag
    const scriptCalls = appendChildSpy.mock.calls.filter((call) => {
      const element = call[0] as HTMLElement;
      return element && element.tagName === 'SCRIPT';
    });

    // Should not append script when YT is already available
    expect(scriptCalls.length).toBe(0);

    appendChildSpy.mockRestore();
  });
});
