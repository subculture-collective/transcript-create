type HitLike = {
  video_id?: string;
  segment_id?: string;
};

export function groupHitsByVideo<T extends HitLike>(hits: T[]): Array<[string, T[]]> {
  const groups = hits.reduce<Map<string, T[]>>((acc, hit) => {
    if (!hit.video_id) return acc;
    acc.set(hit.video_id, [...(acc.get(hit.video_id) ?? []), hit]);
    return acc;
  }, new Map<string, T[]>());
  return Array.from(groups.entries());
}

export function segmentIdsFromHits<T extends HitLike>(hits: T[]): string[] {
  return hits.flatMap((hit) => (hit.segment_id ? [hit.segment_id] : []));
}
