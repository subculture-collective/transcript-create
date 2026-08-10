import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import HomePage from '../routes/HomePage';
import { renderWithProviders } from './test-utils';
import { api } from '../services';
import { http } from '../services/api';
import { AuthProvider } from '../services/auth';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

describe('HomePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders archive hero and summary content', async () => {
    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getArchiveSummary').mockResolvedValue({
      creator_name: 'HasanAra',
      video_count: 12,
      total_duration_seconds: 7260,
      transcript_word_count: 4200,
      updated_at: '2026-05-31T12:00:00Z',
      recent_videos: [
        {
          id: 'video-1',
          youtube_id: 'abc123xyz89',
          title: 'Newest VOD',
          channel_name: 'Channel Alpha',
          duration_seconds: 1800,
          uploaded_at: '2026-05-30T10:00:00Z',
          has_whisper_transcript: true,
          people: [
            { slug: 'guest-one', display_name: 'Guest One', aliases: [] },
            { slug: 'guest-two', display_name: 'Guest Two', aliases: [] },
          ],
          tags: [
            { slug: 'chadvice', label: 'Chadvice', kind: 'category' },
            { slug: 'gaming', label: 'Gaming', kind: 'category' },
          ],
        },
      ],
      popular_searches: [{ term: 'rent', frequency: 9 }],
    } as never);

    const user = userEvent.setup();
    renderWithProviders(<HomePage />);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Find the moment. Read the record.' })
      ).toBeInTheDocument();
    });

    expect(screen.getByPlaceholderText('A topic, quote, guest, or phrase…')).toBeInTheDocument();
    expect(screen.getByLabelText('Search the HasanAbi archive')).toBeInTheDocument();
    expect(screen.getByText('Archived VODs')).toBeInTheDocument();
    expect(screen.getAllByText('Newest VOD').length).toBeGreaterThan(0);
    expect(screen.getByRole('group', { name: 'VOD metadata' })).toBeInTheDocument();
    expect(screen.getByText('Guest One')).toBeInTheDocument();
    expect(screen.getByText('Guest Two')).toBeInTheDocument();
    expect(screen.getByText('Chadvice')).toBeInTheDocument();
    expect(screen.getByText('+1')).toBeInTheDocument();
    expect(screen.queryByText('Gaming')).not.toBeInTheDocument();
    expect(screen.getByText('rent')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'labor' })).toHaveAttribute('href', '/search?q=labor');
    expect(screen.getByRole('link', { name: /rent/ })).toHaveAttribute('href', '/search?q=rent');
    expect(screen.getByRole('link', { name: /Explore the archive/ })).toHaveAttribute(
      'href',
      '/explore'
    );
    expect(screen.getByRole('link', { name: 'Browse every VOD' })).toHaveAttribute(
      'href',
      '/episodes'
    );
    expect(screen.getAllByRole('link', { name: /Newest VOD/ })).toSatisfy((links: HTMLElement[]) =>
      links.some((link) => link.getAttribute('href') === '/v/video-1')
    );
    expect(screen.getByRole('link', { name: /Newest transcript/ })).toHaveAttribute(
      'href',
      '/v/video-1?t=0'
    );

    const input = screen.getByPlaceholderText('A topic, quote, guest, or phrase…');
    await user.type(input, 'archive');
    await user.click(screen.getByRole('button', { name: 'Search archive' }));
    expect(input).toHaveValue('archive');
  });

  it('ignores blank searches and trims a submitted query', async () => {
    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getArchiveSummary').mockResolvedValue({
      recent_videos: [],
      popular_searches: [],
    } as never);
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <HomePage />
          <LocationProbe />
        </AuthProvider>
      </MemoryRouter>
    );

    const input = screen.getByLabelText('Search the HasanAbi archive');
    await user.type(input, '   ');
    await user.click(screen.getByRole('button', { name: 'Search archive' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/');

    await user.clear(input);
    await user.type(input, '  rent control  ');
    await user.click(screen.getByRole('button', { name: 'Search archive' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/search?q=rent%20control');
  });

  it('leaves useful non-loading fallbacks when archive summary is unavailable', async () => {
    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getArchiveSummary').mockRejectedValue(new Error('summary unavailable'));

    renderWithProviders(<HomePage />);

    expect(
      await screen.findByText('Recent VODs will appear when the archive summary is available.')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Search activity will surface useful starting points here.')
    ).toBeInTheDocument();
    expect(screen.queryByText('Loading recent VODs…')).not.toBeInTheDocument();
  });

  it('shows stable placeholders while the archive summary is loading', () => {
    vi.spyOn(http, 'get').mockImplementation(((path: string) => {
      if (path === 'auth/me') {
        return { json: vi.fn().mockResolvedValue({ user: null }) } as never;
      }
      return { json: vi.fn().mockResolvedValue({}) } as never;
    }) as never);
    vi.spyOn(api, 'getArchiveSummary').mockReturnValue(new Promise(() => {}) as never);

    renderWithProviders(<HomePage />);

    expect(screen.getByText('Loading recent VODs…')).toBeInTheDocument();
    expect(screen.getByText('Checking…')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(3);
  });
});
