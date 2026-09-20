import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ExplorePage from '../routes/ExplorePage';
import { api } from '../services';
import { render } from '@testing-library/react';
import axe from 'axe-core';

describe('ExplorePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  const selectedPeriod = {
    slug: '2026-05',
    label: 'May 2026',
    kind: 'month',
    date_from: '2026-05-01',
    date_to: '2026-05-31',
    description: 'A known good archive snapshot.',
    video_count: 2,
    total_duration_seconds: 3600,
  };

  function exploreResponse(
    overrides: Record<string, unknown> = {}
  ): Awaited<ReturnType<typeof api.getExploreIntelligence>> {
    return {
      summary: {
        creator_name: 'HasanAra',
        video_count: 2,
        total_duration_seconds: 3600,
        transcript_word_count: 200,
        recent_videos: [],
        popular_searches: [],
      },
      exploration_modes: [],
      trending_searches: [],
      suggested_searches: [],
      people: [],
      tags: [],
      topic_cards: [],
      periods: [],
      selected_period: selectedPeriod,
      period_options: [selectedPeriod],
      ...overrides,
    } as Awaited<ReturnType<typeof api.getExploreIntelligence>>;
  }

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
    };

    const eventOption = {
      slug: 'launch-day',
      label: 'Launch Day',
      kind: 'event',
      date_from: '2026-05-14',
      date_to: '2026-05-14',
      description: 'A major event day in the archive.',
      video_count: 2,
      total_duration_seconds: 3600,
    };

    const monthOption = {
      slug: '2026-05',
      label: 'May 2026',
      kind: 'month',
      date_from: '2026-05-01',
      date_to: '2026-05-31',
      description: 'The main archive slice for the month.',
      video_count: 12,
      total_duration_seconds: 7200,
    };

    const baseResponse = {
      summary: {
        creator_name: 'HasanAra',
        video_count: 12,
        total_duration_seconds: 7200,
        transcript_word_count: 50000,
        recent_videos: [],
        popular_searches: [],
      },
      exploration_modes: ['timeline', 'topics', 'trending', 'suggested'],
      trending_searches: [{ term: 'ice protests', frequency: 7, trend_score: 7, source: 'hybrid' }],
      suggested_searches: [{ term: 'gaza', frequency: 5, trend_score: 5, source: 'search' }],
      people: [
        { slug: 'guest-one', display_name: 'Guest One', aliases: ['guest one'], role: 'guest' },
      ],
      tags: [{ slug: 'gaming', label: 'Gaming', kind: 'category' }],
      topic_cards: [
        {
          slug: 'ice',
          label: 'ICE',
          kind: 'topic',
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
              video: {
                id: 'video-2',
                youtube_id: 'xyz789',
                title: 'Topic evidence',
                uploaded_at: '2026-05-01T00:00:00Z',
              },
              start_ms: 9000,
              end_ms: 12000,
              snippet: 'ICE is a recurring topic.',
              topic: 'ice',
            },
          ],
        },
        {
          slug: 'okbuddy',
          label: 'Okbuddy',
          kind: 'series',
          source: 'label_assignments',
          status: 'published',
          is_editable: true,
          aliases: [],
          total_moments: 6,
          total_videos: 2,
          recent_mentions_90d: 0,
          trend_score: 12,
          related_topics: [],
          evidence: [
            {
              video: {
                id: 'video-4',
                youtube_id: 'okb123',
                title: 'Okbuddy segment',
                uploaded_at: '2026-05-03T00:00:00Z',
              },
              start_ms: 30000,
              end_ms: 42000,
              snippet: 'Okbuddy segment starts here.',
              topic: 'Okbuddy',
            },
          ],
        },
      ],
      periods: [
        {
          period: 'legacy-may-identifier',
          label: 'May 2026',
          video_count: 2,
          total_duration_seconds: 7200,
          videos: [
            {
              id: 'video-3',
              youtube_id: 'thumb123',
              title: 'Period video',
              uploaded_at: '2026-05-02T00:00:00Z',
              people: [
                { slug: 'guest-one', display_name: 'Guest One', aliases: [], role: 'guest' },
              ],
              tags: [{ slug: 'gaming', label: 'Gaming', kind: 'category' }],
            },
          ],
          top_topics: [
            {
              slug: 'ice',
              label: 'ICE',
              kind: 'topic',
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
          summary: 'May 2026 contains 12 archived VODs and 1 highlighted topic.',
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
    };

    const getExploreIntelligence = vi
      .spyOn(api, 'getExploreIntelligence')
      .mockImplementation(async (opts) => {
        if (opts?.period === weekOption.slug) {
          return { ...baseResponse, selected_period: weekOption };
        }

        if (opts?.period === eventOption.slug) {
          return { ...baseResponse, selected_period: eventOption };
        }

        return baseResponse;
      });

    const { container } = render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Explore the recording archive' })
      ).toBeInTheDocument();
    });
    expect(screen.getByRole('navigation', { name: /Discovery rail/i })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Selected period panel/i })).toBeInTheDocument();

    expect(screen.getByRole('button', { name: 'Latest' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Weeks' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Months' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Leadups' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fallout' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Holidays' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Anniversaries' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Events' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Dates' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Label discovery')).toBeInTheDocument();
    expect(screen.getByLabelText('Selected period')).toBeInTheDocument();

    expect(screen.getByText('2 labels')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Detected topics and stream labels' })
    ).toBeInTheDocument();
    expect(screen.getByText('Topic')).toBeInTheDocument();
    expect(screen.getByText('Series')).toBeInTheDocument();
    expect(
      screen.getAllByRole('link').find((link) => link.getAttribute('href') === '/topics/ICE')
    ).toBeTruthy();
    expect(
      screen.getAllByRole('link').find((link) => link.getAttribute('href') === '/topics/Okbuddy')
    ).toBeTruthy();
    expect(screen.getAllByText(/May 2026.*best available topics/).length).toBeGreaterThan(0);
    expect(
      screen.getByText('May 2026 contains 12 archived VODs and 1 highlighted topic.')
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Guest One' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Gaming' })).toBeInTheDocument();
    expect(screen.getByAltText('Period video')).toHaveAttribute(
      'src',
      expect.stringContaining('thumb123')
    );
    expect(screen.getAllByRole('link', { name: /Open cited moment/i }).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText(/Date from/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Date to/i)).not.toBeInTheDocument();

    expect(getExploreIntelligence).toHaveBeenCalledWith({});
    expect((await axe.run(container)).violations).toEqual([]);
  }, 15_000);

  it('refetches selected predefined periods and latest default', async () => {
    const weekOption = {
      slug: '2026-w22',
      label: 'Week 22, 2026',
      kind: 'week',
      date_from: '2026-05-25',
      date_to: '2026-05-31',
      description: 'A late-May week with fast-moving clips.',
      video_count: 4,
      total_duration_seconds: 8100,
    };

    const eventOption = {
      slug: 'launch-day',
      label: 'Launch Day',
      kind: 'event',
      date_from: '2026-05-14',
      date_to: '2026-05-14',
      description: 'A major event day in the archive.',
      video_count: 2,
      total_duration_seconds: 3600,
    };

    const monthOption = {
      slug: '2026-05',
      label: 'May 2026',
      kind: 'month',
      date_from: '2026-05-01',
      date_to: '2026-05-31',
      description: 'The main archive slice for the month.',
      video_count: 12,
      total_duration_seconds: 7200,
    };

    const response = {
      summary: {
        creator_name: 'HasanAra',
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
    };

    const getExploreIntelligence = vi
      .spyOn(api, 'getExploreIntelligence')
      .mockImplementation(async (opts) => {
        if (opts?.period === weekOption.slug) {
          return { ...response, selected_period: weekOption };
        }

        if (opts?.period === eventOption.slug) {
          return { ...response, selected_period: eventOption };
        }

        return response;
      });
    const getExplorePeriods = vi
      .spyOn(api, 'getExplorePeriods')
      .mockImplementation(async (opts) => ({
        periods: opts?.kind === 'event' ? [eventOption] : [weekOption],
        selected_period: null,
      }));

    render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Explore the recording archive' })
      ).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole('button', { name: 'Weeks' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Week 22, 2026/ })).toBeInTheDocument()
    );
    await waitFor(() =>
      expect(getExplorePeriods).toHaveBeenCalledWith({ kind: 'week', limit: 24 })
    );
    fireEvent.click(screen.getByRole('button', { name: /Week 22, 2026/ }));
    await waitFor(() => {
      expect(getExploreIntelligence).toHaveBeenLastCalledWith({ period: '2026-w22' });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Events' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Launch Day/ })).toBeInTheDocument()
    );
    await waitFor(() =>
      expect(getExplorePeriods).toHaveBeenCalledWith({ kind: 'event', limit: 24 })
    );
    fireEvent.click(screen.getByRole('button', { name: /Launch Day/ }));

    await waitFor(() => {
      expect(getExploreIntelligence).toHaveBeenLastCalledWith({ period: 'launch-day' });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Latest' }));

    await waitFor(() => {
      expect(getExploreIntelligence).toHaveBeenLastCalledWith({});
    });
  });

  it('applies a custom weekly range and preserves the snapshot when refresh fails', async () => {
    let rejectRefresh: ((reason?: unknown) => void) | undefined;
    const getExploreIntelligence = vi
      .spyOn(api, 'getExploreIntelligence')
      .mockResolvedValueOnce(exploreResponse())
      .mockImplementationOnce(
        () =>
          new Promise((_, reject) => {
            rejectRefresh = reject;
          })
      );
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    );

    expect(await screen.findAllByText('A known good archive snapshot.')).not.toHaveLength(0);
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-05-04' } });
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-05-10' } });
    fireEvent.change(screen.getByLabelText('Granularity'), { target: { value: 'week' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply range' }));

    await waitFor(() =>
      expect(getExploreIntelligence).toHaveBeenLastCalledWith({
        period: '2026-05',
        granularity: 'week',
        date_from: '2026-05-04',
        date_to: '2026-05-10',
      })
    );
    expect(screen.getByText('Refreshing')).toBeVisible();
    expect(screen.getAllByText('A known good archive snapshot.')).not.toHaveLength(0);
    rejectRefresh?.(new Error('unavailable'));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The last successful snapshot is still shown.'
    );
    expect(screen.getAllByText('A known good archive snapshot.')).not.toHaveLength(0);
  });

  it('reports predefined-period failures independently and offers a retry', async () => {
    vi.spyOn(api, 'getExploreIntelligence').mockResolvedValue(exploreResponse());
    vi.spyOn(api, 'getExplorePeriods').mockRejectedValue(new Error('unavailable'));

    render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Explore the recording archive' })
      ).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole('button', { name: 'Weeks' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Predefined archive periods');
    expect(screen.getByRole('button', { name: 'Retry predefined periods' })).toBeEnabled();
  });

  it('explains an empty period, topic list, source sections, and discovery facets', async () => {
    const emptyPeriod = {
      ...selectedPeriod,
      description: '',
      video_count: 0,
      total_duration_seconds: 0,
    };
    vi.spyOn(api, 'getExploreIntelligence').mockResolvedValue(
      exploreResponse({
        selected_period: emptyPeriod,
        period_options: [emptyPeriod],
        periods: [
          {
            period: emptyPeriod.slug,
            label: emptyPeriod.label,
            video_count: 0,
            total_duration_seconds: 0,
            videos: [],
            top_topics: [],
            evidence: [],
          },
        ],
      })
    );

    render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/No archived VODs were found for this period/)).toBeVisible();
    expect(screen.getByText('No topic cards are available for this window yet.')).toBeVisible();
    expect(
      screen.getByText('No representative VODs are available for this period yet.')
    ).toBeVisible();
    expect(
      screen.getByText('No cited moments are available for this selected period yet.')
    ).toBeVisible();
    expect(screen.getByText('No people facets yet.')).toBeVisible();
    expect(screen.getByText('No tag facets yet.')).toBeVisible();
  });

  it('explains when no calculated source material exists', async () => {
    vi.spyOn(api, 'getExploreIntelligence').mockResolvedValue(exploreResponse());

    render(
      <MemoryRouter initialEntries={['/explore']}>
        <ExplorePage />
      </MemoryRouter>
    );

    expect(
      await screen.findByText('No calculated source material is available for this period yet.')
    ).toBeVisible();
  });
});
