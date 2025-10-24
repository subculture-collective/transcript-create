import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api, http } from '../services/api'

// Mock ky
vi.mock('ky', () => ({
  default: {
    create: () => ({
      get: vi.fn(),
      post: vi.fn(),
      delete: vi.fn(),
    }),
  },
}))

describe('api service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('search', () => {
    it('calls API with correct parameters', async () => {
      const mockResponse = { hits: [] }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      await api.search('test query')

      expect(getMock).toHaveBeenCalledWith(
        'search',
        expect.objectContaining({
          searchParams: expect.any(URLSearchParams),
        })
      )
    })

    it('includes optional parameters', async () => {
      const mockResponse = { hits: [] }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      await api.search('test', {
        source: 'youtube',
        video_id: 'abc123',
        limit: 10,
        offset: 5,
      })

      const call = getMock.mock.calls[0]
      const params = call[1].searchParams as URLSearchParams
      expect(params.get('q')).toBe('test')
      expect(params.get('source')).toBe('youtube')
      expect(params.get('video_id')).toBe('abc123')
      expect(params.get('limit')).toBe('10')
      expect(params.get('offset')).toBe('5')
    })

    it('returns search results', async () => {
      const mockResponse = {
        hits: [
          {
            id: 1,
            video_id: 'video1',
            start_ms: 1000,
            end_ms: 2000,
            snippet: 'test snippet',
          },
        ],
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.search('test')
      expect(result).toEqual(mockResponse)
    })
  })

  describe('getTranscript', () => {
    it('calls correct endpoint', async () => {
      const mockResponse = {
        video_id: 'video1',
        segments: [],
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      await api.getTranscript('video1')

      expect(getMock).toHaveBeenCalledWith('videos/video1/transcript')
    })

    it('returns transcript data', async () => {
      const mockResponse = {
        video_id: 'video1',
        segments: [
          { start_ms: 0, end_ms: 1000, text: 'Hello world', speaker_label: null },
        ],
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.getTranscript('video1')
      expect(result).toEqual(mockResponse)
    })
  })

  describe('getVideo', () => {
    it('calls correct endpoint', async () => {
      const mockResponse = {
        id: 'video1',
        youtube_id: 'abc123',
        title: 'Test Video',
        duration_seconds: 120,
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      await api.getVideo('video1')

      expect(getMock).toHaveBeenCalledWith('videos/video1')
    })

    it('returns video info', async () => {
      const mockResponse = {
        id: 'video1',
        youtube_id: 'abc123',
        title: 'Test Video',
        duration_seconds: 120,
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.getVideo('video1')
      expect(result).toEqual(mockResponse)
    })
  })
})
