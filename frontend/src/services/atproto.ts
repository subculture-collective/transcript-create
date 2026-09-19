import { BrowserOAuthClient, type OAuthSession } from '@atproto/oauth-client-browser';
import { http } from './api';

export type ATConnection = { client: BrowserOAuthClient; session?: OAuthSession; resolver: string };
// One init per document, including React StrictMode renders. Errors can be retried
// by reloading this standalone page; callbacks are never processed twice.
const invalidationListeners = new Set<(sub: string) => void>();
export function onATInvalidated(listener: (sub: string) => void) {
  invalidationListeners.add(listener);
  return () => {
    invalidationListeners.delete(listener);
  };
}
let initialization: Promise<ATConnection> | undefined;
export function initializeAT() {
  initialization ??= (async () => {
    const config = await http
      .get('atproto/config')
      .json<{ client_id: string; handle_resolver: string }>();
    const client = await BrowserOAuthClient.load({
      clientId: config.client_id,
      handleResolver: config.handle_resolver,
      onSessionDeleted: (sub) => {
        for (const listener of invalidationListeners) listener(sub);
      },
    });
    const restored = await client.init();
    return { client, session: restored?.session, resolver: config.handle_resolver };
  })();
  return initialization;
}

export function checkedPassage(value: string | null, origin: string): string | undefined {
  if (!value) return;
  let url: URL;
  try {
    url = new URL(value, origin);
  } catch {
    return;
  }
  if (url.origin !== origin || !/^\/api\/share\/videos\/[0-9a-f-]{36}$/i.test(url.pathname)) return;
  const start = url.searchParams.get('start_ms');
  const end = url.searchParams.get('end_ms');
  if (
    !start ||
    !end ||
    !/^\d+$/.test(start) ||
    !/^\d+$/.test(end) ||
    !Number.isSafeInteger(Number(end)) ||
    Number(end) <= Number(start)
  )
    return;
  url.hash = '';
  return url.href;
}

export function createPublicRecord(body: string, passage?: string) {
  const text = body.trim();
  const graphemes = [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(text)]
    .length;
  if (!text || graphemes > 300 || new TextEncoder().encode(text).length > 3000)
    throw new Error('Use between 1 and 300 characters.');
  if (passage && new URL(passage).protocol !== 'https:')
    throw new Error('Passage sharing requires a publicly reachable HTTPS archive.');
  return {
    $type: 'app.bsky.feed.post' as const,
    text,
    createdAt: new Date().toISOString(),
    ...(passage
      ? {
          embed: {
            $type: 'app.bsky.embed.external' as const,
            external: {
              uri: passage,
              title: 'Watch this passage in context',
              description: 'Open the source recording and selected transcript passage.',
            },
          },
        }
      : {}),
  };
}

export async function publishAT(
  session: OAuthSession,
  record: ReturnType<typeof createPublicRecord>,
  rkey: string
) {
  // The official SDK resolves the verified session's PDS and handles DPoP/refresh.
  // Stable key prevents duplicate records on an ambiguous retry.
  const response = await session.fetchHandler('/xrpc/com.atproto.repo.createRecord', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo: session.sub, collection: 'app.bsky.feed.post', rkey, record }),
  });
  if (!response.ok) throw new Error('Provider did not confirm publication');
  const data: { uri?: string } = await response.json();
  const expected = `at://${session.sub}/app.bsky.feed.post/${rkey}`;
  if (data.uri !== expected) throw new Error('Provider returned an unexpected record');
  return data.uri;
}
