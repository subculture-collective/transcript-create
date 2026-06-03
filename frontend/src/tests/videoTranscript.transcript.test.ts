import { describe, expect, it } from 'vitest';
import { buildTranscriptTurns, normalizeTranscriptText } from '../features/videoTranscript/transcript';

describe('video transcript kernels', () => {
  it('normalizes spacing without changing words', () => {
    expect(normalizeTranscriptText('Hello   world !')).toBe('Hello world!');
  });

  it('groups unlabeled paragraphs and preserves match hints', () => {
    const turns = buildTranscriptTurns(
      [
        { start_ms: 0, end_ms: 1000, text: 'First sentence.', speaker_label: null },
        { start_ms: 1100, end_ms: 1800, text: 'Second sentence.', speaker_label: null },
        { start_ms: 4000, end_ms: 5000, text: 'New thought.', speaker_label: null },
        { start_ms: 6000, end_ms: 7000, text: 'Speaker line.', speaker_label: 'Hasan' },
        { start_ms: 7100, end_ms: 7600, text: 'Speaker line two.', speaker_label: 'Hasan' },
      ],
      [{ start_ms: 6200, end_ms: 6300, video_id: 'v1', id: 9, snippet: '<mark>match</mark>' } as never]
    );

    expect(turns).toHaveLength(3);
    expect(turns[0].segments).toHaveLength(2);
    expect(turns[1].segments).toHaveLength(1);
    expect(turns[2].speaker).toBe('Hasan');
    expect(turns[2].segments[0].match?.id).toBe(9);
    expect(turns[2].segments).toHaveLength(2);
  });
});
