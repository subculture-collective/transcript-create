import { describe, expect, it } from 'vitest';
import { groupHitsByVideo, segmentIdsFromHits } from '../features/searchTranscript/matches';

describe('search transcript matches', () => {
  it('groups hits by video id', () => {
    const hits = [
      { video_id: 'v1', segment_id: 's1' },
      { video_id: 'v2', segment_id: 's2' },
      { video_id: 'v1', segment_id: 's3' },
    ];

    expect(groupHitsByVideo(hits)).toEqual([
      ['v1', [hits[0], hits[2]]],
      ['v2', [hits[1]]],
    ]);
  });

  it('preserves first-seen group order for integer-like video ids', () => {
    const hits = [
      { video_id: '10', segment_id: 's1' },
      { video_id: '2', segment_id: 's2' },
    ];

    expect(groupHitsByVideo(hits).map(([videoId]) => videoId)).toEqual(['10', '2']);
  });

  it('extracts segment ids in order', () => {
    const hits = [{ segment_id: 'a' }, { segment_id: 'b' }, {}];

    expect(segmentIdsFromHits(hits)).toEqual(['a', 'b']);
  });
});
