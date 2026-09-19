import { describe, expect, it, vi } from 'vitest';
import { checkedPassage, createPublicRecord, publishAT } from '../services/atproto';
import type { OAuthSession } from '@atproto/oauth-client-browser';
describe('AT public sharing boundaries', () => {
  it('only attaches a valid passage from this archive', () => {
    const path = '/api/share/videos/00000000-0000-0000-0000-000000000902?start_ms=1&end_ms=10';
    expect(checkedPassage(path, 'https://archive.example')).toBe(`https://archive.example${path}`);
    expect(
      checkedPassage(`https://elsewhere.example${path}`, 'https://archive.example')
    ).toBeUndefined();
    expect(checkedPassage('/account', 'https://archive.example')).toBeUndefined();
    expect(
      checkedPassage(path.replace('end_ms=10', 'end_ms=0'), 'https://archive.example')
    ).toBeUndefined();
  });
  it('uses standard Bluesky records and validates graphemes and public links', () => {
    const record = createPublicRecord('A passage', 'https://archive.example/api/share/videos/demo');
    expect(record.$type).toBe('app.bsky.feed.post');
    expect(record.embed?.$type).toBe('app.bsky.embed.external');
    expect(() => createPublicRecord('x'.repeat(301))).toThrow();
    expect(() => createPublicRecord('  ')).toThrow();
    expect(() => createPublicRecord('Passage', 'http://127.0.0.1/demo')).toThrow();
    expect(createPublicRecord('🙂'.repeat(300)).text).toBe('🙂'.repeat(300));
  });
  it('writes only to the verified SDK session DID and retains the retry key', async () => {
    const fetchHandler = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ uri: 'at://did:plc:example/app.bsky.feed.post/draft-key' }),
    });
    const record = createPublicRecord('A deliberate public post');
    const session = { sub: 'did:plc:example', fetchHandler } as unknown as OAuthSession;
    await publishAT(session, record, 'draft-key');
    expect(fetchHandler).toHaveBeenCalledWith('/xrpc/com.atproto.repo.createRecord', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo: 'did:plc:example',
        collection: 'app.bsky.feed.post',
        rkey: 'draft-key',
        record,
      }),
    });
  });
});
