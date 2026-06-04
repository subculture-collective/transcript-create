import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ExplorePage from '../routes/ExplorePage'
import { api } from '../services'
import { render } from '@testing-library/react'

describe('ExplorePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders archive intelligence sections, controls, and evidence links', async () => {
    const getExploreIntelligence = vi.spyOn(api, 'getExploreIntelligence').mockResolvedValue({
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
          status: 'published',
          is_editable: true,
          aliases: ['ice'],
          total_moments: 14,
          total_videos: 3,
          recent_mentions_90d: 2,
          trend_score: 14,
          related_topics: [],
          evidence: [
            {
              video: { id: 'video-2', youtube_id: 'xyz789', title: 'Topic evidence', uploaded_at: '2026-05-01T00:00:00Z' },
              start_ms: 9000,
              end_ms: 12000,
              snippet: 'ICE is a recurring topic.',
              topic: 'ice',
            },
          ],
        },
      ],
      periods: [
        {
          period: '2026-05',
          label: 'May 2026',
          video_count: 2,
          total_duration_seconds: 5400,
          videos: [
            { id: 'video-3', youtube_id: 'thumb123', title: 'Period video', uploaded_at: '2026-05-02T00:00:00Z' },
          ],
          top_topics: [
            {
              slug: 'ice',
              label: 'ICE',
              source: 'hybrid',
              aliases: [],
              total_moments: 10,
              total_videos: 2,
              recent_mentions_90d: 1,
              trend_score: 10,
              related_topics: [],
              evidence: [],
            },
          ],
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
    expect(screen.getByRole('navigation', { name: /Explore sections/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute('href', '#overview')
    expect(screen.getByRole('link', { name: 'Trending' })).toHaveAttribute('href', '#trending')
    expect(screen.getByRole('link', { name: 'Suggested' })).toHaveAttribute('href', '#suggested')
    expect(screen.getByRole('link', { name: 'Topic Atlas' })).toHaveAttribute('href', '#topics')
    expect(screen.getByRole('link', { name: 'Timeline' })).toHaveAttribute('href', '#timeline')
    expect(screen.getByRole('link', { name: 'Method' })).toHaveAttribute('href', '#method')

    expect(screen.getByRole('button', { name: 'Month' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Week' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '8' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Date from')).toHaveValue('')
    expect(screen.getByLabelText('Date to')).toHaveValue('')

    expect(screen.getByText('topics')).toBeInTheDocument()
    expect(screen.getByText('ice protests')).toBeInTheDocument()
    expect(screen.getAllByRole('link').find((link) => link.getAttribute('href') === '/topics/ICE')).toBeTruthy()
    expect(screen.getByText('Published')).toBeInTheDocument()
    expect(screen.getByText('Editable')).toBeInTheDocument()
    expect(screen.getByText('Hybrid')).toBeInTheDocument()
    expect(screen.getByText('May 2026')).toBeInTheDocument()
    expect(screen.getByAltText('Period video')).toHaveAttribute('src', expect.stringContaining('thumb123'))
    expect(screen.getByText('May 2026 contains 2 archived VODs and 1 highlighted topic.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open cited moment/i })).toHaveAttribute('href', '/v/video-1?t=1171')
    expect(screen.getByText(/Topics are a hybrid of curated labels and automatic discovery/i)).toBeInTheDocument()

    expect(getExploreIntelligence).toHaveBeenCalledWith({ granularity: 'month', topic_limit: 8, period_limit: 8 })
  })

  it('submits intelligence filters with params', async () => {
    const getExploreIntelligence = vi.spyOn(api, 'getExploreIntelligence').mockResolvedValue({
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
      periods: [],
    })

    render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Archive Intelligence' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Week' }))
    fireEvent.click(screen.getByRole('button', { name: '12' }))
    const from = screen.getByLabelText('Date from')
    const to = screen.getByLabelText('Date to')
    fireEvent.change(from, { target: { value: '2026-05-01' } })
    fireEvent.change(to, { target: { value: '2026-05-31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => {
      expect(getExploreIntelligence).toHaveBeenLastCalledWith({
        granularity: 'week',
        topic_limit: 12,
        period_limit: 8,
        date_from: '2026-05-01',
        date_to: '2026-05-31',
      })
    })
  })
})
