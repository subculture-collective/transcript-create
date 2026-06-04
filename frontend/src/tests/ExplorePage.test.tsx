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
    const weekOption = {
      slug: '2026-w22',
      label: 'Week 22, 2026',
      kind: 'week',
      date_from: '2026-05-25',
      date_to: '2026-05-31',
      description: 'A late-May week with fast-moving clips.',
      video_count: 4,
      total_duration_seconds: 8100,
    }

    const eventOption = {
      slug: 'launch-day',
      label: 'Launch Day',
      kind: 'event',
      date_from: '2026-05-14',
      date_to: '2026-05-14',
      description: 'A major event day in the archive.',
      video_count: 2,
      total_duration_seconds: 3600,
    }

    const monthOption = {
      slug: '2026-05',
      label: 'May 2026',
      kind: 'month',
      date_from: '2026-05-01',
      date_to: '2026-05-31',
      description: 'The main archive slice for the month.',
      video_count: 12,
      total_duration_seconds: 7200,
    }

    const baseResponse = {
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
      selected_period: monthOption,
      period_options: [monthOption, weekOption, eventOption],
    }

    const getExploreIntelligence = vi.spyOn(api, 'getExploreIntelligence').mockImplementation(async (opts) => {
      if (opts?.period === weekOption.slug) {
        return { ...baseResponse, selected_period: weekOption }
      }

      if (opts?.period === eventOption.slug) {
        return { ...baseResponse, selected_period: eventOption }
      }

      return baseResponse
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

    expect(screen.getByRole('button', { name: 'Latest' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Weeks' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Months' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Events' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Dates' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '8 topics' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByLabelText('Date from')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Date to')).not.toBeInTheDocument()

    expect(screen.getByText('1 topics')).toBeInTheDocument()
    expect(screen.getByText('ice protests')).toBeInTheDocument()
    expect(screen.getAllByRole('link').find((link) => link.getAttribute('href') === '/topics/ICE')).toBeTruthy()
    expect(screen.queryByText('Published')).not.toBeInTheDocument()
    expect(screen.queryByText('Editable')).not.toBeInTheDocument()
    expect(screen.queryByText('Hybrid')).not.toBeInTheDocument()
    expect(screen.getAllByText('May 2026 · 2026-05-01 → 2026-05-31 · 8 topics').length).toBeGreaterThan(0)
    expect(screen.getByText('Predefined periods are materialized by a backfill/refresher pipeline, so Explore shows consistent slices instead of live date-window guesses.')).toBeInTheDocument()
    expect(screen.getByAltText('Period video')).toHaveAttribute('src', expect.stringContaining('thumb123'))
    expect(screen.getByText('May 2026 contains 2 archived VODs and 1 highlighted topic.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open cited moment/i })).toHaveAttribute('href', '/v/video-1?t=1171')
    expect(screen.getByText(/Predefined periods are materialized by a backfill\/refresher pipeline/i)).toBeInTheDocument()

    expect(getExploreIntelligence).toHaveBeenCalledWith({ topic_limit: 8 })
  })

  it('refetches selected predefined periods and topic counts with the current period', async () => {
    const weekOption = {
      slug: '2026-w22',
      label: 'Week 22, 2026',
      kind: 'week',
      date_from: '2026-05-25',
      date_to: '2026-05-31',
      description: 'A late-May week with fast-moving clips.',
      video_count: 4,
      total_duration_seconds: 8100,
    }

    const eventOption = {
      slug: 'launch-day',
      label: 'Launch Day',
      kind: 'event',
      date_from: '2026-05-14',
      date_to: '2026-05-14',
      description: 'A major event day in the archive.',
      video_count: 2,
      total_duration_seconds: 3600,
    }

    const monthOption = {
      slug: '2026-05',
      label: 'May 2026',
      kind: 'month',
      date_from: '2026-05-01',
      date_to: '2026-05-31',
      description: 'The main archive slice for the month.',
      video_count: 12,
      total_duration_seconds: 7200,
    }

    const response = {
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
      selected_period: monthOption,
      period_options: [monthOption, weekOption, eventOption],
    }

    const getExploreIntelligence = vi.spyOn(api, 'getExploreIntelligence').mockImplementation(async (opts) => {
      if (opts?.period === weekOption.slug) {
        return { ...response, selected_period: weekOption }
      }

      if (opts?.period === eventOption.slug) {
        return { ...response, selected_period: eventOption }
      }

      return response
    })

    render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    )

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Archive Intelligence' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Weeks' }))
    await waitFor(() => expect(screen.getByText('Week 22, 2026')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Week 22, 2026'))
    await waitFor(() => {
      expect(getExploreIntelligence).toHaveBeenLastCalledWith({ period: '2026-w22', topic_limit: 8 })
    })

    fireEvent.click(screen.getByRole('button', { name: '12 topics' }))
    await waitFor(() => {
      expect(getExploreIntelligence).toHaveBeenLastCalledWith({ period: '2026-w22', topic_limit: 12 })
    })

    fireEvent.click(screen.getByRole('button', { name: 'Events' }))
    await waitFor(() => expect(screen.getByText('Launch Day')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Launch Day'))

    await waitFor(() => {
      expect(getExploreIntelligence).toHaveBeenLastCalledWith({ period: 'launch-day', topic_limit: 12 })
    })

    fireEvent.click(screen.getByRole('button', { name: '16 topics' }))

    await waitFor(() => {
      expect(getExploreIntelligence).toHaveBeenLastCalledWith({
        period: 'launch-day',
        topic_limit: 16,
      })
    })
  })
})
