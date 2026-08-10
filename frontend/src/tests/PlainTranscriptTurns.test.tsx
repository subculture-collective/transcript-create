import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PlainTranscriptTurns from '../components/video/PlainTranscriptTurns';

describe('PlainTranscriptTurns', () => {
  it('renders search matches as inert text with code-point highlights', () => {
    const { container } = render(
      <PlainTranscriptTurns
        source="whisper"
        turns={[
          {
            key: 'paragraph-1',
            speaker: null,
            segments: [
              {
                id: 1,
                segment: { start_ms: 0, end_ms: 1000, text: 'Transcript sentence.' },
                match: {
                  id: 10,
                  video_id: 'video-1',
                  start_ms: 0,
                  end_ms: 1000,
                  snippet: `🚀 rent — 日本語 “quoted” <img src=x onerror=alert(1)> ${'x'.repeat(200)}`,
                  highlights: [{ start: 2, end: 6 }],
                },
              },
            ],
          },
        ]}
        activeSegId={null}
        isSavedSegment={() => false}
        onClickSegment={vi.fn()}
        onSaveMoment={vi.fn()}
        onCopyQuote={vi.fn()}
      />
    );

    expect(screen.getByText('rent', { selector: 'mark' })).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent(
      `🚀 rent — 日本語 “quoted” <img src=x onerror=alert(1)> ${'x'.repeat(200)}`
    );
    expect(container.querySelector('img')).not.toBeInTheDocument();
  });
});
