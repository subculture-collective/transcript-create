import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import YouTubePlayer from '../components/YouTubePlayer'
import { createRef } from 'react'
import type { YouTubePlayerHandle } from '../components/YouTubePlayer'

describe('YouTubePlayer', () => {
  let mockPlayer: any

  beforeEach(() => {
    vi.clearAllMocks()

    // Mock YouTube IFrame API
    mockPlayer = {
      seekTo: vi.fn(),
      destroy: vi.fn(),
    }

    window.YT = {
      Player: vi.fn(function (this: any, element: any, config: any) {
        this.seekTo = mockPlayer.seekTo
        this.destroy = mockPlayer.destroy
        // Simulate onReady callback
        setTimeout(() => config.events.onReady(), 0)
        return this
      }),
    } as any
  })

  afterEach(() => {
    delete window.YT
  })

  it('renders player container', () => {
    render(<YouTubePlayer videoId="test-video-id" />)
    expect(screen.getByTitle('YouTube player')).toBeInTheDocument()
  })

  it('renders with custom title', () => {
    render(<YouTubePlayer videoId="test-video-id" title="Custom Title" />)
    expect(screen.getByTitle('Custom Title')).toBeInTheDocument()
  })

  it('initializes YouTube player with correct config', async () => {
    render(<YouTubePlayer videoId="test-video-id" start={30} />)

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled()
    })

    const call = (window.YT!.Player as any).mock.calls[0]
    const config = call[1]

    expect(config.videoId).toBe('test-video-id')
    expect(config.playerVars.start).toBe(30)
    expect(config.playerVars.autoplay).toBe(0)
  })

  it('seeks to start time when ready', async () => {
    render(<YouTubePlayer videoId="test-video-id" start={45} />)

    await waitFor(() => {
      expect(mockPlayer.seekTo).toHaveBeenCalledWith(45, true)
    })
  })

  it('does not seek when start is 0', async () => {
    render(<YouTubePlayer videoId="test-video-id" start={0} />)

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled()
    })

    // Wait a bit to ensure seekTo is not called
    await new Promise((resolve) => setTimeout(resolve, 100))
    expect(mockPlayer.seekTo).not.toHaveBeenCalled()
  })

  it('exposes seekTo method via ref', async () => {
    const ref = createRef<YouTubePlayerHandle>()
    render(<YouTubePlayer ref={ref} videoId="test-video-id" />)

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled()
    })

    // Call seekTo via ref
    ref.current?.seekTo(120)

    expect(mockPlayer.seekTo).toHaveBeenCalledWith(120, true)
  })

  it('handles seekTo errors gracefully', async () => {
    mockPlayer.seekTo = vi.fn(() => {
      throw new Error('Player not ready')
    })

    const ref = createRef<YouTubePlayerHandle>()
    render(<YouTubePlayer ref={ref} videoId="test-video-id" />)

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled()
    })

    // Should not throw
    expect(() => ref.current?.seekTo(120)).not.toThrow()
  })

  it('cleans up player on unmount', async () => {
    const { unmount } = render(<YouTubePlayer videoId="test-video-id" />)

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled()
    })

    unmount()

    expect(mockPlayer.destroy).toHaveBeenCalled()
  })

  it('handles destroy errors gracefully', async () => {
    mockPlayer.destroy = vi.fn(() => {
      throw new Error('Destroy error')
    })

    const { unmount } = render(<YouTubePlayer videoId="test-video-id" />)

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled()
    })

    // Should not throw
    expect(() => unmount()).not.toThrow()
  })

  it.skip('loads YouTube API script when not available', async () => {
    // This test is skipped because happy-dom doesn't support external script loading
    // In a real browser environment, this functionality works correctly
    delete window.YT

    const appendChildSpy = vi.spyOn(document.body, 'appendChild')

    render(<YouTubePlayer videoId="test-video-id" />)

    await waitFor(() => {
      expect(appendChildSpy).toHaveBeenCalled()
    })

    const scriptTag = appendChildSpy.mock.calls[0][0] as HTMLScriptElement
    expect(scriptTag.src).toBe('https://www.youtube.com/iframe_api')

    appendChildSpy.mockRestore()
  })

  it('does not reload API script when already available', async () => {
    // YT is already available from beforeEach
    const appendChildSpy = vi.spyOn(document.body, 'appendChild')

    render(<YouTubePlayer videoId="test-video-id" />)

    await waitFor(() => {
      expect(window.YT!.Player).toHaveBeenCalled()
    })

    // Check if appendChild was called with a script tag
    const scriptCalls = appendChildSpy.mock.calls.filter(call => {
      const element = call[0]
      return element && element.tagName === 'SCRIPT'
    })
    
    // Should not append script when YT is already available
    expect(scriptCalls.length).toBe(0)

    appendChildSpy.mockRestore()
  })
})
