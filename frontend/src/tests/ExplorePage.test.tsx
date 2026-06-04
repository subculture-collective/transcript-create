import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ExplorePage from '../routes/ExplorePage'
import { api } from '../services'
import { render } from '@testing-library/react'

describe('ExplorePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders archive intelligence sections and evidence links', async () => {
    vi.spyOn(api, 'getExploreIntelligence').mockResolvedValue({
      summary: {
        creator_name: 'HasAnAra',
        video_count: 12,
        total_duration_seconds: 7200,
        transcript_word_count: 50000,
        recent_videos: [],
        popular_searches: [],
      },
      exploration_modes: ['timeline', 'topics', 'trending', 'suggested'],
      trending_searches: [{ term: 'ice protests', frequency: 7, trend_score: 7, source: 'hybrid' }],
      suggested_searches: [{ term: 'gaza', frequency: 5, trend_score: 5, source: 'search' }],
      topic_cards: [
        {
          slug: 'ice',
          label: 'ICE',
          source: 'hybrid',
          aliases: ['ice'],
          total_moments: 14,
          total_videos: 3,
          recent_mentions_90d: 2,
          trend_score: 14,
          related_topics: [],
          evidence: [],
        },
      ],
      periods: [
        {
          period: '2026-05',
          label: 'May 2026',
          video_count: 2,
          total_duration_seconds: 5400,
          videos: [],
          top_topics: [],
          summary: 'May 2026 contains 2 archived VODs and 1 highlighted topic.',
          evidence: [
            {
              video: { id: 'video-1', youtube_id: 'abc123', title: 'Evidence VOD' },
              start_ms: 1171000,
              end_ms: 1175000,
              snippet: 'ICE protests were discussed.',
              topic: 'ice',
            },
          ],
        },
      ],
    })

    render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Archive Intelligence' })).toBeInTheDocument()
    })
    expect(screen.getByText('ice protests')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /ICE hybrid 14 moments 3 VODs/i })).toHaveAttribute('href', '/topics/ICE')
    expect(screen.getByText('May 2026 contains 2 archived VODs and 1 highlighted topic.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open cited moment/i })).toHaveAttribute('href', '/v/video-1?t=1171')
  })
})
