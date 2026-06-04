import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api, http, apiListSavedSearches } from '../services/api'

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
        category: 'news',
        video_id: 'abc123',
        limit: 10,
        offset: 5,
      })

      const call = getMock.mock.calls[0]
      const params = call[1].searchParams as URLSearchParams
      expect(params.get('q')).toBe('test')
      expect(params.get('source')).toBe('youtube')
      expect(params.get('category')).toBe('news')
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

  describe('searchGrouped', () => {
    it('calls the grouped search endpoint', async () => {
      const mockResponse = { total_moments: 0, total_videos: 0, groups: [] }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      await api.searchGrouped('rent', { date_from: '2026-05-01', source: 'native', category: 'interview' })

      const params = getMock.mock.calls[0][1].searchParams as URLSearchParams
      expect(params.get('q')).toBe('rent')
      expect(params.get('source')).toBe('native')
      expect(params.get('date_from')).toBe('2026-05-01')
      expect(params.get('category')).toBe('interview')
    })
  })

  describe('getMentionMap', () => {
    it('calls the mention map endpoint and returns mini-report fields', async () => {
      const mockResponse = {
        query: 'ai',
        total_moments: 83,
        total_videos: 5,
        first_mentioned_year: 2021,
        most_discussed_period: '2024',
        most_discussed_count: 30,
        recent_mentions_90d: 6,
        related_topics: ['copyright', 'openai'],
        top_episodes_count: 5,
        top_episodes: [],
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.getMentionMap('ai', { category: 'interview' })

      expect(result).toEqual(mockResponse)
      expect(getMock).toHaveBeenCalledWith('search/mention-map', { searchParams: expect.any(URLSearchParams) })
      const params = getMock.mock.calls[0][1].searchParams as URLSearchParams
      expect(params.get('q')).toBe('ai')
      expect(params.get('category')).toBe('interview')
    })
  })

  describe('getExploreIntelligence', () => {
    it('calls archive intelligence endpoint', async () => {
      const mockResponse = {
        summary: {
          creator_name: 'HasAnAra',
          video_count: 1,
          total_duration_seconds: 3600,
          transcript_word_count: 200,
          recent_videos: [],
          popular_searches: [],
        },
        exploration_modes: ['timeline', 'topics', 'trending', 'suggested'],
        trending_searches: [],
        suggested_searches: [],
        topic_cards: [],
        people: [],
        tags: [],
        periods: [],
        selected_period: null,
        period_options: [],
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.getExploreIntelligence()

      expect(result).toEqual(mockResponse)
      expect(getMock).toHaveBeenCalledWith('archive/intelligence')
    })

    it('passes through intelligence query params including period', async () => {
      const mockResponse = {
        summary: {
          creator_name: 'HasAnAra',
          video_count: 1,
          total_duration_seconds: 3600,
          transcript_word_count: 200,
          recent_videos: [],
          popular_searches: [],
        },
        exploration_modes: [],
        trending_searches: [],
        suggested_searches: [],
        topic_cards: [],
        people: [],
        tags: [],
        periods: [],
        selected_period: null,
        period_options: [],
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      await api.getExploreIntelligence({
        period: '2026-05',
        topic_limit: 12,
        granularity: 'week',
        period_limit: 16,
        date_from: '2026-05-01',
        date_to: '2026-05-31',
      })

      expect(getMock).toHaveBeenCalledWith(
        'archive/intelligence',
        expect.objectContaining({ searchParams: expect.any(URLSearchParams) })
      )
      const params = getMock.mock.calls[0][1].searchParams as URLSearchParams
      expect(params.get('period')).toBe('2026-05')
      expect(params.get('granularity')).toBe('week')
      expect(params.get('topic_limit')).toBe('12')
      expect(params.get('period_limit')).toBe('16')
      expect(params.get('date_from')).toBe('2026-05-01')
      expect(params.get('date_to')).toBe('2026-05-31')
    })
  })

  describe('getExplorePeriods', () => {
    it('calls the predefined periods endpoint', async () => {
      const mockResponse = { items: [] }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.getExplorePeriods({ kind: 'week', limit: 16 })

      expect(result).toEqual(mockResponse)
      expect(getMock).toHaveBeenCalledWith('archive/intelligence/periods', {
        searchParams: expect.any(URLSearchParams),
      })
      const params = getMock.mock.calls[0][1].searchParams as URLSearchParams
      expect(params.get('kind')).toBe('week')
      expect(params.get('limit')).toBe('16')
    })
  })

  describe('saved searches', () => {
    it('lists saved searches', async () => {
      const mockResponse = { items: [] }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await apiListSavedSearches()
      expect(result).toEqual(mockResponse)
      expect(getMock).toHaveBeenCalledWith('users/me/saved-searches')
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

      expect(getMock).toHaveBeenCalledWith('videos/video1/transcript', {
        searchParams: { mode: 'formatted', source: 'best' },
      })
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

  describe('listRecentVideos', () => {
    it('unwraps paginated response items', async () => {
      const mockResponse = {
        items: [
          {
            id: 'video1',
            youtube_id: 'abc123',
            title: 'Test Video',
          },
        ],
        page_info: {
          has_next_page: false,
          has_previous_page: false,
          next_cursor: null,
          previous_cursor: null,
          total_count: 1,
        },
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.listRecentVideos(12)

      expect(result).toEqual(mockResponse.items)
      expect(getMock).toHaveBeenCalledWith('videos', {
        searchParams: { completed_only: 'true', limit: '12' },
      })
    })

    it('tolerates legacy array video response', async () => {
      const legacyResponse = [
        {
          id: 'video1',
          youtube_id: 'abc123',
          title: 'Legacy Video',
        },
      ]
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(legacyResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.listRecentVideos(12)

      expect(result).toEqual(legacyResponse)
    })
  })

  describe('listStreamLibrary', () => {
    it('lists stream library with filters', async () => {
      const mockResponse = {
        items: [],
        page_info: {
          has_next_page: false,
          has_previous_page: false,
          next_cursor: null,
          previous_cursor: null,
          total_count: 0,
        },
      }
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(mockResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.listStreamLibrary({
        limit: 24,
        offset: 48,
        completed_only: true,
        q: 'hasan',
        category: 'interview',
        date_field: 'uploaded_at',
        date_from: '2026-05-01',
        date_to: '2026-05-31',
      })

      expect(result).toEqual(mockResponse)
      expect(getMock).toHaveBeenCalledWith('videos', {
        searchParams: {
          limit: '24',
          offset: '48',
          completed_only: 'true',
          q: 'hasan',
          category: 'interview',
          date_field: 'uploaded_at',
          date_from: '2026-05-01',
          date_to: '2026-05-31',
        },
      })
    })

    it('normalizes legacy array response for stream library', async () => {
      const legacyResponse = [
        {
          id: 'video1',
          youtube_id: 'abc123',
          title: 'Legacy Video',
        },
      ]
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue(legacyResponse),
      })
      vi.spyOn(http, 'get').mockImplementation(getMock)

      const result = await api.listStreamLibrary({ limit: 12 })

      expect(result.items).toEqual(legacyResponse)
      expect(result.page_info.total_count).toBe(1)
    })
  })
})
