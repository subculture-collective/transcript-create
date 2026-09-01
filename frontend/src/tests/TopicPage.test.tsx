import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import TopicPage from '../routes/TopicPage';
import { api } from '../services';
import { favorites } from '../services/favorites';
import { http } from '../services/api';
import { renderWithProviders } from './test-utils';
import axe from 'axe-core';

let currentTopic = 'rent';
let initialTimelineParams = new URLSearchParams();
const serviceMocks = vi.hoisted(() => ({ addFavorite: vi.fn() }));

vi.mock('../services', async () => {
  const actual = await vi.importActual<typeof import('../services')>('../services');
  return { ...actual, apiAddFavorite: serviceMocks.addFavorite, track: vi.fn() };
});

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  const React = await vi.importActual<typeof import('react')>('react');
  return {
    ...actual,
    useParams: () => ({ query: currentTopic }),
    useSearchParams: () => {
      const [params, setParams] = React.useState(() => new URLSearchParams(initialTimelineParams));
      return [params, (next: URLSearchParams) => setParams(new URLSearchParams(next))] as const;
    },
  };
});

function minimalMentionMap() {
  return {
    query: 'rent',
    total_moments: 1,
    total_videos: 1,
    first_mentioned_year: 2026,
    most_discussed_period: '2026',
    most_discussed_count: 1,
    recent_mentions_90d: 1,
    related_topics: [],
    top_episodes_count: 1,
    query_time_ms: 3,
    first_mention: null,
    latest_mention: null,
    top_episodes: [
      {
        video: { id: 'video-1', title: 'VOD one', channel_name: 'Channel Alpha' },
        moments: [
          {
            id: 11,
            video_id: 'video-1',
            start_ms: 1000,
            end_ms: 2000,
            snippet: 'first <mark>rent</mark> mention',
            source: 'whisper',
          },
        ],
      },
    ],
  } as never;
}

describe('TopicPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    currentTopic = 'rent';
    initialTimelineParams = new URLSearchParams();
    serviceMocks.addFavorite.mockResolvedValue({ id: 'favorite-1' });

    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn() },
      configurable: true,
    });

    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
  });

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
            title: 'VOD one',
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
            title: 'VOD two',
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
    } as never);

    const toggleMock = vi.spyOn(favorites, 'toggle');

    const { container } = renderWithProviders(<TopicPage />);

    await waitFor(() => {
      expect(mentionMapMock).toHaveBeenCalledWith('rent');
    });

    expect(screen.getByText('Query').parentElement).toHaveTextContent('“rent”');
    expect(screen.getByText('First mentioned').parentElement).toHaveTextContent('2021');
    expect(screen.getByText('Most discussed').parentElement).toHaveTextContent('2024');
    expect(screen.getByText('Most discussed').parentElement).toHaveTextContent('3 moments');
    expect(screen.getByText('Recent mentions').parentElement).toHaveTextContent('6');
    expect(screen.getByText('Related topics').parentElement).toHaveTextContent('copyright');
    expect(screen.getAllByText('Top VODs')[0].parentElement).toHaveTextContent('5');
    expect(screen.getByText('Total moments').parentElement).toHaveTextContent('4');
    expect(screen.getByText('VODs').parentElement).toHaveTextContent('2');
    expect(screen.getByText('First mention')).toBeInTheDocument();
    expect(screen.getByText('Latest mention')).toBeInTheDocument();
    expect(screen.getAllByText('Top VODs').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: 'Play all matches' })).toHaveLength(2);
    expect(screen.getAllByText('rent', { selector: 'mark' })).toHaveLength(5);
    fireEvent.click(screen.getAllByRole('button', { name: 'Copy quote' })[0]);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('/v/video-1?t=1&source=whisper#moment-whisper-1000')
    );
    expect(await screen.findByRole('status')).toHaveTextContent('Quote copied.');

    fireEvent.click(screen.getAllByRole('button', { name: 'Save moment' })[0]);
    expect(toggleMock).toHaveBeenCalledWith(
      expect.objectContaining({ videoId: 'video-1', segIndex: 11, startMs: 1000, endMs: 2000 })
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Saved moment' })).toBeInTheDocument();
    });
    expect((await axe.run(container)).violations).toEqual([]);
  });

  it('announces a mention-map failure without crashing the rest of the topic route', async () => {
    vi.spyOn(api, 'getMentionMap').mockRejectedValue(new Error('search unavailable'));
    vi.spyOn(api, 'getTopicTimeline').mockResolvedValue({ buckets: [] } as never);
    vi.spyOn(api, 'getTopicOpinions').mockResolvedValue({ items: [] } as never);

    renderWithProviders(<TopicPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Topic page failed to load.');
    expect(screen.getByRole('heading', { name: 'Topic: rent' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Timeline range' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open search' })).toHaveAttribute(
      'href',
      '/search?q=rent'
    );
  });

  it('persists timeline filters in the URL and distinguishes loading, empty, and failure states', async () => {
    let resolveTimeline:
      | ((value: Awaited<ReturnType<typeof api.getTopicTimeline>>) => void)
      | undefined;
    const timelineMock = vi
      .spyOn(api, 'getTopicTimeline')
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveTimeline = resolve;
          })
      )
      .mockRejectedValue(new DOMException('unavailable', 'AbortError'));
    vi.spyOn(api, 'getMentionMap').mockResolvedValue(minimalMentionMap());
    vi.spyOn(api, 'getTopicOpinions').mockResolvedValue({ items: [] } as never);

    renderWithProviders(<TopicPage />);

    expect(await screen.findByRole('status')).toHaveTextContent('Loading topic timeline…');
    resolveTimeline?.({ topic: 'rent', granularity: 'month', buckets: [] });
    expect(await screen.findByText('No mentions were found in this range.')).toBeVisible();

    fireEvent.change(screen.getByLabelText('Granularity'), { target: { value: 'week' } });
    await waitFor(() => expect(screen.getByLabelText('Granularity')).toHaveValue('week'));
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-05-01' } });
    await waitFor(() => expect(screen.getByLabelText('From')).toHaveValue('2026-05-01'));
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-05-31' } });

    await waitFor(() => {
      expect(screen.getByLabelText('Granularity')).toHaveValue('week');
      expect(screen.getByLabelText('From')).toHaveValue('2026-05-01');
      expect(screen.getByLabelText('To')).toHaveValue('2026-05-31');
      expect(timelineMock).toHaveBeenLastCalledWith(
        'rent',
        {
          granularity: 'week',
          date_from: '2026-05-01',
          date_to: '2026-05-31',
        },
        expect.any(AbortSignal)
      );
    });
    expect(await screen.findByText('Topic timeline is temporarily unavailable.')).toBeVisible();
  });

  it('keeps topic evidence visible when opinion history fails', async () => {
    vi.spyOn(api, 'getMentionMap').mockResolvedValue(minimalMentionMap());
    vi.spyOn(api, 'getTopicTimeline').mockResolvedValue({ buckets: [] } as never);
    vi.spyOn(api, 'getTopicOpinions').mockRejectedValue(
      new DOMException('unavailable', 'AbortError')
    );

    renderWithProviders(<TopicPage />);

    expect(await screen.findByText('Opinion history is temporarily unavailable.')).toBeVisible();
    expect(screen.getAllByText('VOD one')).not.toHaveLength(0);
    expect(screen.getByText('rent', { selector: 'mark' })).toBeVisible();
  });

  it('announces quote-copy failure without hiding the topic moment', async () => {
    vi.spyOn(api, 'getMentionMap').mockResolvedValue(minimalMentionMap());
    vi.spyOn(api, 'getTopicTimeline').mockResolvedValue({ buckets: [] } as never);
    vi.spyOn(api, 'getTopicOpinions').mockResolvedValue({ items: [] } as never);
    vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error('denied'));

    renderWithProviders(<TopicPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Copy quote' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('The quote could not be copied.');
    expect(screen.getByText('rent', { selector: 'mark' })).toBeVisible();
  });

  it('saves a topic moment remotely for an authenticated user', async () => {
    vi.mocked(http.get).mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: { id: 'user-1' } }) } as never;
      }
      if (path === 'auth/csrf') {
        return { json: vi.fn().mockResolvedValue({ csrf_token: 'csrf-token' }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getMentionMap').mockResolvedValue(minimalMentionMap());
    vi.spyOn(api, 'getTopicTimeline').mockResolvedValue({ buckets: [] } as never);
    vi.spyOn(api, 'getTopicOpinions').mockResolvedValue({ items: [] } as never);

    renderWithProviders(<TopicPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Save moment' }));

    expect(serviceMocks.addFavorite).toHaveBeenCalledWith({
      video_id: 'video-1',
      start_ms: 1000,
      end_ms: 2000,
      text: 'first rent mention',
    });
    expect(await screen.findByRole('button', { name: 'Saved moment' })).toBeDisabled();
  });

  it('reports save failure without marking the topic moment saved', async () => {
    vi.spyOn(api, 'getMentionMap').mockResolvedValue(minimalMentionMap());
    vi.spyOn(api, 'getTopicTimeline').mockResolvedValue({ buckets: [] } as never);
    vi.spyOn(api, 'getTopicOpinions').mockResolvedValue({ items: [] } as never);
    vi.spyOn(favorites, 'toggle').mockImplementation(() => {
      throw new Error('storage unavailable');
    });
    vi.spyOn(console, 'error').mockImplementation(() => {});

    renderWithProviders(<TopicPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Save moment' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save that moment.');
    expect(screen.getByRole('button', { name: 'Save moment' })).toBeEnabled();
  });

  it('records opinion corrections and retractions with reasons and revision history', async () => {
    vi.mocked(http.get).mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return {
          json: vi.fn().mockResolvedValue({
            user: { id: 'admin-1' },
            capabilities: ['admin:access'],
          }),
        } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getMentionMap').mockResolvedValue(minimalMentionMap());
    vi.spyOn(api, 'getTopicTimeline').mockResolvedValue({ buckets: [] } as never);
    const revision = {
      revision: 1,
      stance: 'support',
      summary: 'Original summary.',
      confidence: 0.9,
      model_version: 'model-1',
      prompt_version: 'prompt-1',
      time_bucket: '2026-Q2',
      model_generated: true,
      status: 'published',
      created_at: '2026-07-12T00:00:00Z',
      evidence: [],
    };
    const opinion = {
      id: 'opinion-1',
      subject_slug: 'rent',
      normalized_claim: 'Rent should be affordable',
      status: 'published',
      current_revision: 1,
      revisions: [revision],
    };
    const corrected = {
      ...opinion,
      current_revision: 2,
      revisions: [
        revision,
        {
          ...revision,
          revision: 2,
          summary: 'Corrected summary.',
          correction_reason: 'Source wording changed',
        },
      ],
    };
    const retracted = {
      ...corrected,
      status: 'retracted',
      current_revision: 3,
      revisions: [
        ...corrected.revisions,
        {
          ...revision,
          revision: 3,
          status: 'retracted',
          summary: 'Retracted summary.',
          correction_reason: 'No longer supported',
        },
      ],
    };
    vi.spyOn(api, 'getTopicOpinions')
      .mockResolvedValueOnce({ items: [opinion] } as never)
      .mockResolvedValueOnce({ items: [corrected] } as never)
      .mockResolvedValue({ items: [retracted] } as never);
    const correct = vi
      .spyOn(api, 'correctOpinion')
      .mockResolvedValue({ items: [corrected] } as never);
    const retract = vi
      .spyOn(api, 'retractOpinion')
      .mockResolvedValue({ items: [retracted] } as never);
    Object.defineProperty(window, 'prompt', {
      configurable: true,
      value: vi
        .fn()
        .mockReturnValueOnce('Source wording changed')
        .mockReturnValueOnce('No longer supported'),
    });

    renderWithProviders(<TopicPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Correct' }));

    await waitFor(() =>
      expect(correct).toHaveBeenCalledWith('opinion-1', { reason: 'Source wording changed' })
    );
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Opinion correction recorded as a new revision.'
    );
    expect(await screen.findByText('Revision history (2)')).toBeInTheDocument();
    expect(screen.getByText(/Source wording changed/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retract' }));
    await waitFor(() => expect(retract).toHaveBeenCalledWith('opinion-1', 'No longer supported'));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Opinion retracted with revision history preserved.'
    );
    expect(await screen.findByText('Revision history (3)')).toBeInTheDocument();
    expect(screen.getByText(/No longer supported/)).toBeInTheDocument();
  });

  it('shows a recovery state instead of fetching an invalid empty topic', () => {
    currentTopic = '';
    const mentionMapMock = vi.spyOn(api, 'getMentionMap');

    renderWithProviders(<TopicPage />);

    expect(screen.getByText('Pick a topic from search results first.')).toBeVisible();
    expect(mentionMapMock).not.toHaveBeenCalled();
  });
});
