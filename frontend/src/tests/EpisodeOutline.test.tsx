import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import EpisodeOutline from '../components/video/EpisodeOutline';

const chapters = [
  {
    chapter_index: 0,
    start_ms: 0,
    end_ms: 600_000,
    title: 'Opening discussion',
    summary: 'The episode opens with the news.',
    confidence_score: 1,
    status: 'published',
    source: 'transcript' as const,
    evidence: [
      { block_index: 0, start_ms: 0, end_ms: 20_000, text: 'The episode opens with the news.' },
    ],
  },
  {
    chapter_index: 1,
    start_ms: 600_000,
    end_ms: 1_200_000,
    title: 'Rally coverage',
    summary: 'Coverage moves to the rally.',
    confidence_score: 1,
    status: 'published',
    source: 'transcript' as const,
    evidence: [
      { block_index: 4, start_ms: 600_000, end_ms: 620_000, text: 'Coverage moves to the rally.' },
    ],
  },
];

describe('EpisodeOutline', () => {
  it('marks the current chapter and navigates to another chapter', () => {
    const onSelect = vi.fn();
    render(<EpisodeOutline chapters={chapters} currentMs={650_000} onSelect={onSelect} />);

    expect(screen.getByRole('button', { name: /Rally coverage/ })).toHaveAttribute(
      'aria-current',
      'location'
    );
    expect(screen.getByText(/Evidence · transcript at/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Opening discussion/ }));
    expect(onSelect).toHaveBeenCalledWith(chapters[0]);
  });
});
