import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import TopicPage from '../routes/TopicPage'
import { api } from '../services'
import { favorites } from '../services/favorites'
import { http } from '../services/api'
import { renderWithProviders } from './test-utils'

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useParams: () => ({ query: 'rent' }),
  }
})

describe('TopicPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn() },
      configurable: true,
    })

    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never
      }
      return { json: vi.fn().mockResolvedValue({}) } as never
    }) as never)
  })

  it('renders mention map stats, first/latest mentions, and grouped actions', async () => {
    const mentionMapMock = vi.spyOn(api, 'getMentionMap').mockResolvedValue({
      query: 'rent',
      total_moments: 4,
      total_videos: 2,
      first_mentioned_year: 2021,
      most_discussed_period: '2024',
      most_discussed_count: 3,
      recent_mentions_90d: 6,
      related_topics: ['copyright', 'openai', 'labor', 'automation', 'art'],
      top_episodes_count: 5,
      query_time_ms: 9,
      first_mention: {
        id: 11,
        video_id: 'video-1',
        start_ms: 1000,
        end_ms: 2000,
        snippet: 'first <mark>rent</mark> mention',
        source: 'whisper',
        video: { id: 'video-1' },
      },
      latest_mention: {
        id: 22,
        video_id: 'video-2',
        start_ms: 3000,
        end_ms: 4000,
        snippet: 'latest <mark>rent</mark> mention',
        source: 'youtube',
        video: { id: 'video-2' },
      },
      top_episodes: [
        {
          video: {
            id: 'video-1',
            youtube_id: 'abc123',
            title: 'Episode one',
            channel_name: 'Channel Alpha',
            duration_seconds: 3600,
            uploaded_at: '2026-05-10T00:00:00Z',
          },
          moments: [
            {
              id: 11,
              video_id: 'video-1',
              start_ms: 1000,
              end_ms: 2000,
              snippet: 'first <mark>rent</mark> mention',
              source: 'whisper',
            },
            {
              id: 12,
              video_id: 'video-1',
              start_ms: 5000,
              end_ms: 6000,
              snippet: 'another <mark>rent</mark> mention',
              source: 'whisper',
            },
          ],
        },
        {
          video: {
            id: 'video-2',
            youtube_id: 'def456',
            title: 'Episode two',
            channel_name: 'Channel Beta',
            duration_seconds: 1800,
            uploaded_at: '2026-05-12T00:00:00Z',
          },
          moments: [
            {
              id: 22,
              video_id: 'video-2',
              start_ms: 3000,
              end_ms: 4000,
              snippet: 'latest <mark>rent</mark> mention',
              source: 'youtube',
            },
          ],
        },
      ],
    } as never)

    const toggleMock = vi.spyOn(favorites, 'toggle')

    renderWithProviders(<TopicPage />)

    await waitFor(() => {
      expect(mentionMapMock).toHaveBeenCalledWith('rent')
    })

    expect(screen.getByText('Query').parentElement).toHaveTextContent('“rent”')
    expect(screen.getByText('First mentioned').parentElement).toHaveTextContent('2021')
    expect(screen.getByText('Most discussed').parentElement).toHaveTextContent('2024')
    expect(screen.getByText('Most discussed').parentElement).toHaveTextContent('3 moments')
    expect(screen.getByText('Recent mentions').parentElement).toHaveTextContent('6')
    expect(screen.getByText('Related topics').parentElement).toHaveTextContent('copyright')
    expect(screen.getAllByText('Top episodes')[0].parentElement).toHaveTextContent('5')
    expect(screen.getByText('Total moments').parentElement).toHaveTextContent('4')
    expect(screen.getByText('Episodes').parentElement).toHaveTextContent('2')
    expect(screen.getByText('First mention')).toBeInTheDocument()
    expect(screen.getByText('Latest mention')).toBeInTheDocument()
    expect(screen.getAllByText('Top episodes').length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: 'Play all matches' })).toHaveLength(2)
    fireEvent.click(screen.getAllByRole('button', { name: 'Copy quote' })[0])
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('/v/video-1?t=1#seg-11')
    )

    fireEvent.click(screen.getAllByRole('button', { name: 'Save moment' })[0])
    expect(toggleMock).toHaveBeenCalledWith(
      expect.objectContaining({ videoId: 'video-1', segIndex: 11, startMs: 1000, endMs: 2000 })
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Saved moment' })).toBeInTheDocument()
    })
  })
})
