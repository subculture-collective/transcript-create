import type { Segment } from '../../types/api';

export type TopicCandidate = {
  key: string;
  label: string;
  /** Phrases that count as a mention; the label is always included. */
  terms: string[];
  kind: 'topic' | 'tag' | 'person' | 'search';
};

export type TopicMention = {
  segmentIndex: number;
  startMs: number;
  text: string;
};

export type EpisodeTopic = TopicCandidate & {
  count: number;
  mentions: TopicMention[];
};

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function termPattern(terms: string[]) {
  const unique = [...new Set(terms.map((term) => term.trim()).filter((term) => term.length > 1))];
  if (unique.length === 0) return null;
  // Longest first so "Donald Trump" wins over "Trump" inside the alternation.
  unique.sort((left, right) => right.length - left.length);
  return new RegExp(
    `(?<![\\p{L}\\p{N}])(?:${unique.map(escapeRegExp).join('|')})(?![\\p{L}\\p{N}])`,
    'giu'
  );
}

/**
 * Locate archive topics, tags, people and popular searches inside one episode's
 * transcript. The result is a client-side reading aid: counts are literal
 * phrase matches, not the archive's topic classifier.
 */
export function findEpisodeTopics(
  segments: Segment[],
  candidates: TopicCandidate[],
  { minCount = 1, limit = 24 }: { minCount?: number; limit?: number } = {}
): EpisodeTopic[] {
  if (segments.length === 0 || candidates.length === 0) return [];
  const seen = new Set<string>();
  const results: EpisodeTopic[] = [];

  for (const candidate of candidates) {
    const identity = candidate.label.trim().toLowerCase();
    if (!identity || seen.has(identity)) continue;
    seen.add(identity);
    const pattern = termPattern([candidate.label, ...candidate.terms]);
    if (!pattern) continue;

    const mentions: TopicMention[] = [];
    let count = 0;
    segments.forEach((segment, segmentIndex) => {
      pattern.lastIndex = 0;
      const matches = segment.text.match(pattern);
      if (!matches) return;
      count += matches.length;
      mentions.push({ segmentIndex, startMs: segment.start_ms, text: segment.text });
    });

    if (count >= minCount) results.push({ ...candidate, count, mentions });
  }

  return results
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
    .slice(0, limit);
}
