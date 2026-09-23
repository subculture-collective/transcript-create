import { describe, expect, it } from 'vitest';
import { findEpisodeTopics } from '../features/videoTranscript/topics';

const segments = [
  { start_ms: 0, end_ms: 1000, text: 'We talked about Gaza and the ICE raids.' },
  { start_ms: 1000, end_ms: 2000, text: 'Gazans were mentioned, but that is not a match.' },
  { start_ms: 2000, end_ms: 3000, text: 'Back to gaza. GAZA again, and ice cream.' },
  { start_ms: 3000, end_ms: 4000, text: 'Donald Trump spoke; Trump then left.' },
];

describe('findEpisodeTopics', () => {
  it('counts whole-word mentions with aliases and records where they occur', () => {
    const topics = findEpisodeTopics(segments, [
      { key: 'topic:gaza', label: 'Gaza', terms: [], kind: 'topic' },
      { key: 'topic:ice', label: 'ICE', terms: [], kind: 'topic' },
      { key: 'topic:trump', label: 'Trump', terms: ['Donald Trump'], kind: 'topic' },
    ]);

    expect(topics.map((topic) => [topic.label, topic.count])).toEqual([
      ['Gaza', 3],
      ['ICE', 2],
      ['Trump', 2],
    ]);
    const gaza = topics[0];
    expect(gaza.mentions.map((mention) => mention.startMs)).toEqual([0, 2000]);
  });

  it('drops duplicates, unmatched candidates, and escapes regex characters', () => {
    const topics = findEpisodeTopics(segments, [
      { key: 'a', label: 'Gaza', terms: [], kind: 'topic' },
      { key: 'b', label: 'gaza', terms: [], kind: 'search' },
      { key: 'c', label: 'C++ (lang)', terms: [], kind: 'tag' },
    ]);
    expect(topics.map((topic) => topic.key)).toEqual(['a']);
    expect(findEpisodeTopics([], [{ key: 'a', label: 'Gaza', terms: [], kind: 'topic' }])).toEqual(
      []
    );
  });
});
