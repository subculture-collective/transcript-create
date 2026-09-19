import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import MomentActionRow from '../components/archive/MomentActionRow';
import { renderWithRouter } from './test-utils';

describe('MomentActionRow', () => {
  it('exposes the primary and secondary moment actions with accessible controls', () => {
    renderWithRouter(
      <MomentActionRow
        videoId="video-1"
        moment={{
          id: 4_864_024,
          video_id: 'video-1',
          start_ms: 1140,
          end_ms: 2000,
          snippet: 'Quote',
          source: 'whisper',
        }}
        query="housing"
        saved={false}
        onOpenTimestamp={vi.fn()}
        onCopyTimestamp={vi.fn()}
        onCopyQuote={vi.fn()}
        onSaveMoment={vi.fn()}
      />
    );

    expect(screen.getByRole('button', { name: 'Copy quote' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save moment' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open moment' })).toHaveAttribute(
      'href',
      '/v/video-1?t=1&t_ms=1140#moment-1140'
    );
    expect(screen.getByRole('link', { name: 'Share passage' })).toHaveAttribute(
      'href',
      '/v/video-1?t=1&t_ms=1140&end_ms=2000#moment-1140'
    );
    expect(screen.getByRole('button', { name: 'Copy link' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Copy quote' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Full VOD' })).toHaveAttribute('href', '/v/video-1');
  });
});
