import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';

function mockJsonResponse<T>(value: T) {
  return { json: () => Promise.resolve(value) };
}

vi.mock('../services/api', () => ({
  http: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { http } from '../services/api';
import AdminChapterReview from '../routes/admin/AdminChapterReview';

const candidateSet = {
  video_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  youtube_id: 'yt-1',
  video_title: 'A chapter review VOD',
  duration_seconds: 600,
  chapters: [
    {
      id: '11111111-1111-1111-1111-111111111111',
      video_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      chapter_index: 0,
      start_ms: 0,
      end_ms: 300000,
      title: 'Opening News Discussion',
      summary: 'The stream opens with a sustained news discussion.',
      confidence_score: 0.75,
      status: 'candidate',
      source: 'automatic',
      evidence: [{ block_index: 0, start_ms: 0, end_ms: 60000, text: 'Election news evidence' }],
      pipeline_version: 'pipeline-v2',
      model_name: 'qwen3:8b',
      prompt_version: 'prompt-v2',
      transcript_source: 'youtube',
    },
    {
      id: '22222222-2222-2222-2222-222222222222',
      video_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      chapter_index: 1,
      start_ms: 300000,
      end_ms: 600000,
      title: 'Housing Policy Debate',
      summary: 'The discussion turns to housing policy.',
      confidence_score: 0.8,
      status: 'candidate',
      source: 'automatic',
      evidence: [
        { block_index: 1, start_ms: 300000, end_ms: 360000, text: 'Housing policy evidence' },
      ],
      pipeline_version: 'pipeline-v2',
      model_name: 'qwen3:8b',
      prompt_version: 'prompt-v2',
      transcript_source: 'youtube',
    },
  ],
} as const;

describe('AdminChapterReview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(http.get).mockReturnValue(mockJsonResponse({ items: [candidateSet] }) as never);
    vi.mocked(http.post).mockReturnValue(mockJsonResponse(candidateSet) as never);
  });

  it('shows provenance and evidence and publishes the edited complete set', async () => {
    render(
      <BrowserRouter>
        <AdminChapterReview />
      </BrowserRouter>
    );

    expect((await screen.findAllByText('A chapter review VOD')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('qwen3:8b')).toHaveLength(2);

    const user = userEvent.setup();
    await user.click(screen.getAllByText('Evidence (1)')[1]);
    expect(screen.getByText('Housing policy evidence')).toBeInTheDocument();
    await user.clear(screen.getByLabelText('Chapter 2 title'));
    await user.type(screen.getByLabelText('Chapter 2 title'), 'Rent and Housing Policy');
    await user.clear(
      screen.getByLabelText('Start (seconds)', {
        selector: '#chapter-start-22222222-2222-2222-2222-222222222222',
      })
    );
    await user.type(
      screen.getByLabelText('Start (seconds)', {
        selector: '#chapter-start-22222222-2222-2222-2222-222222222222',
      }),
      '360'
    );
    await user.type(screen.getByLabelText('Review note'), 'Boundary follows the topic change');
    await user.click(screen.getByRole('button', { name: 'Publish reviewed set' }));

    await waitFor(() => {
      expect(vi.mocked(http.post)).toHaveBeenCalledWith(
        'admin/archive/videos/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/chapters/review',
        expect.objectContaining({
          json: expect.objectContaining({
            action: 'publish',
            reason: 'Boundary follows the topic change',
            chapters: expect.arrayContaining([
              expect.objectContaining({
                id: '22222222-2222-2222-2222-222222222222',
                start_ms: 360000,
                title: 'Rent and Housing Policy',
              }),
            ]),
          }),
        })
      );
    });
    expect(
      await screen.findByText('Published 2 reviewed chapters for this VOD.')
    ).toBeInTheDocument();
  }, 15_000);

  it('can trigger review-only generation for an editor-selected video', async () => {
    vi.mocked(http.post).mockReturnValue(mockJsonResponse({ chapters: 12 }) as never);
    render(
      <BrowserRouter>
        <AdminChapterReview />
      </BrowserRouter>
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Video ID'), 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
    await user.click(screen.getByRole('button', { name: 'Generate candidates' }));

    await waitFor(() => {
      expect(vi.mocked(http.post)).toHaveBeenCalledWith(
        'admin/archive/enrichment/generate/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
      );
    });
    expect(await screen.findByText(/Generated 12 review-only chapters/)).toBeInTheDocument();
  }, 15_000);

  it('does not send partial UUID filters while an editor is typing', async () => {
    render(
      <BrowserRouter>
        <AdminChapterReview />
      </BrowserRouter>
    );

    await screen.findAllByText('A chapter review VOD');
    expect(vi.mocked(http.get)).toHaveBeenCalledTimes(1);

    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText('Filter by video ID'),
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    );
    expect(vi.mocked(http.get)).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(vi.mocked(http.get)).toHaveBeenCalledTimes(2));
    const secondCall = vi.mocked(http.get).mock.calls[1];
    expect(String(secondCall[1]?.searchParams)).toContain(
      'video_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    );
  });
});
