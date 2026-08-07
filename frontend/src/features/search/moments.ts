import type { SearchHit } from '../../types/api';
import { buildTimestampLink, formatTimestamp } from '../archive/format';

export function plainTextFromSnippet(snippet: string) {
  return snippet
    .replace(/<mark>/gi, '')
    .replace(/<\/mark>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function buildQuoteText(
  videoId: string,
  moment: SearchHit,
  title: string,
  origin = window.location.origin
) {
  const url = `${origin}${buildTimestampLink(videoId, moment.start_ms, moment.source)}`;
  return `“${plainTextFromSnippet(moment.snippet)}”\n\n— ${title}, ${formatTimestamp(moment.start_ms)}\n${url}`;
}

export function buildPlayMatchesLink(videoId: string, moment: SearchHit, query: string) {
  const seconds = Math.floor(moment.start_ms / 1000);
  const params = new URLSearchParams({ t: String(seconds), q: query, play: 'matches' });
  if (moment.source) params.set('source', moment.source);
  const anchor = moment.source ? `#moment-${moment.source}-${moment.start_ms}` : '';
  return `/v/${videoId}?${params.toString()}${anchor}`;
}
