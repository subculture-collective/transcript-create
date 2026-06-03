import type { SearchHit, Segment } from '../../types/api';

export type TranscriptTurn = {
  key: string;
  speaker: string | null;
  segments: Array<{ segment: Segment; id: number; match?: SearchHit }>;
};

function speakerName(seg: Segment) {
  return seg.speaker_label?.trim() || null;
}

export function normalizeTranscriptText(text: string) {
  return text
    .replace(/\s+/g, ' ')
    .replace(/\s+([,.!?;:])/g, '$1')
    .trim();
}

export function shouldStartNewUnlabeledParagraph(
  previous: { segment: Segment; id: number; match?: SearchHit } | undefined,
  current: Segment,
  currentText: string
) {
  if (!previous) return true;

  const previousText = normalizeTranscriptText(previous.segment.text);
  const silenceGapMs = current.start_ms - previous.segment.end_ms;
  const previousEndsSentence = /[.!?]["')\]]?$/.test(previousText);
  const currentLooksLikeNewThought = /^[A-Z0-9"'“‘]/.test(currentText);
  const previousWordCount = previousText.split(/\s+/).filter(Boolean).length;

  return silenceGapMs >= 1200 || (previousEndsSentence && currentLooksLikeNewThought && previousWordCount >= 8);
}

export function buildTranscriptTurns(segments: Segment[], hits: SearchHit[] | null): TranscriptTurn[] {
  return segments.reduce<TranscriptTurn[]>((turns, segment, idx) => {
    const id = idx + 1;
    const speaker = speakerName(segment);
    const match = hits?.find((h) => h.start_ms >= segment.start_ms && h.start_ms < segment.end_ms);
    const last = turns.at(-1);
    const currentText = normalizeTranscriptText(segment.text);

    if (!currentText) return turns;

    if (!speaker) {
      const previous = last?.segments.at(-1);
      if (last && last.speaker === null && !shouldStartNewUnlabeledParagraph(previous, segment, currentText)) {
        last.segments.push({ segment, id, match });
        return turns;
      }

      turns.push({
        key: `paragraph-${id}`,
        speaker: null,
        segments: [{ segment, id, match }],
      });
      return turns;
    }

    if (last?.speaker === speaker) {
      last.segments.push({ segment, id, match });
      return turns;
    }

    turns.push({
      key: `${speaker}-${id}`,
      speaker,
      segments: [{ segment, id, match }],
    });
    return turns;
  }, []);
}
