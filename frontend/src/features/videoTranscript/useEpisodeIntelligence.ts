import { useEffect, useState } from 'react';
import { api } from '../../services';
import type { QuotedMoment, RelatedEpisode } from '../../types/api';

export type EpisodeIntelligenceState = {
  related: RelatedEpisode[] | null;
  quoted: QuotedMoment[] | null;
  error: boolean;
};

export function useEpisodeIntelligence(videoId: string): EpisodeIntelligenceState {
  const [state, setState] = useState<EpisodeIntelligenceState>({
    related: null,
    quoted: null,
    error: false,
  });
  useEffect(() => {
    const controller = new AbortController();
    setState({ related: null, quoted: null, error: false });
    void Promise.all([
      api.getRelatedEpisodes(videoId, controller.signal),
      api.getQuotedMoments(videoId, controller.signal),
    ])
      .then(([relatedResponse, quotedResponse]) =>
        setState({
          related: relatedResponse.items ?? [],
          quoted: quotedResponse.items ?? [],
          error: false,
        })
      )
      .catch(() => {
        if (!controller.signal.aborted) setState({ related: null, quoted: null, error: true });
      });
    return () => controller.abort();
  }, [videoId]);
  return state;
}
