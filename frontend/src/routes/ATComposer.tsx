import { useEffect, useState } from 'react';
import {
  initializeAT,
  onATInvalidated,
  checkedPassage,
  createPublicRecord,
  publishAT,
  type ATConnection,
} from '../services/atproto';

export default function ATComposer() {
  const [connection, setConnection] = useState<ATConnection>();
  const [handle, setHandle] = useState('');
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [consent, setConsent] = useState(false);
  const [postUrl, setPostUrl] = useState('');
  const [attempt, setAttempt] = useState<{
    record: ReturnType<typeof createPublicRecord>;
    rkey: string;
  }>();
  const [passage] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const selected = checkedPassage(params.get('passage'), window.location.origin);
    if (selected) sessionStorage.setItem('at-passage', selected);
    else if (!window.location.hash.includes('state=')) sessionStorage.removeItem('at-passage');
    return selected ?? checkedPassage(sessionStorage.getItem('at-passage'), window.location.origin);
  });
  useEffect(() => {
    let active = true;
    const invalidated = (sub: string) => {
      if (active)
        setConnection((previous) =>
          previous?.session?.sub === sub ? { ...previous, session: undefined } : previous
        );
    };
    let unsubscribe = () => {};
    initializeAT()
      .then((next) => {
        if (!active) return;
        setConnection(next);
        unsubscribe = onATInvalidated(invalidated);
      })
      .catch(() => {
        if (active)
          setError(
            'AT connection is unavailable. It may be disabled, misconfigured, or the authorization may have expired. Reload to retry.'
          );
      });
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);
  async function connect() {
    if (!connection) return;
    setBusy(true);
    setError('');
    try {
      await connection.client.signInRedirect(handle.trim(), { state: crypto.randomUUID() });
    } catch {
      setError('Connection was cancelled or failed. Check the handle or provider and try again.');
      setBusy(false);
    }
  }
  async function publish() {
    if (!connection?.session || !consent) return;
    setBusy(true);
    setError('');
    try {
      const next = attempt ?? {
        record: createPublicRecord(body, passage),
        rkey: crypto.randomUUID(),
      };
      setAttempt(next);
      await publishAT(connection.session, next.record, next.rkey);
      setPostUrl(
        `https://bsky.app/profile/${encodeURIComponent(connection.session.sub)}/post/${next.rkey}`
      );
    } catch (failure) {
      setError(
        failure instanceof Error && failure.message.startsWith('Use between')
          ? failure.message
          : 'Publishing did not return confirmation. Check your profile before starting another post. Retrying this draft uses the same record key to prevent duplicates.'
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-2xl px-4 py-10 space-y-6">
      <a href="/community" className="action-link">
        ← Return to the archive community
      </a>
      <header>
        <p className="eyebrow">Public sharing</p>
        <h1 className="page-title">Your account. Your post.</h1>
        <p className="mt-4 text-muted">
          Connect an existing Bluesky or AT Protocol account from its current provider. No account
          migration is required.
        </p>
      </header>
      {error && (
        <p role="alert" className="surface-card">
          {error}
        </p>
      )}
      {!connection && !error && <p role="status">Loading account connection…</p>}
      {connection && !connection.session && (
        <form
          className="surface-card space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void connect();
          }}
        >
          <label className="block">
            Handle, DID, or provider URL
            <input
              className="form-control mt-2"
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              placeholder="you.example.com"
              required
              maxLength={2048}
              autoComplete="off"
            />
          </label>
          <p className="text-sm text-muted">
            Your provider will ask permission to create public Bluesky posts. Handle lookup uses{' '}
            {connection.resolver}; that service receives your handle and IP address. Credentials
            stay in this browser’s OAuth storage.
          </p>
          <button className="btn-primary" disabled={busy || !handle.trim()}>
            Continue to my provider
          </button>
        </form>
      )}
      {connection?.session && (
        <>
          <section className="surface-card space-y-3">
            <h2 className="section-title">Connected account</h2>
            <p className="break-all">{connection.session.sub}</p>
            <p className="text-sm text-muted">
              This connection is separate from your archive login. It does not grant site roles or
              publish anything automatically.
            </p>
            <button
              className="btn-secondary"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await connection.client.revoke(connection.session!.sub);
                  setConnection({ ...connection, session: undefined });
                  setAttempt(undefined);
                  setPostUrl('');
                  setConsent(false);
                } catch {
                  setError(
                    'Could not confirm disconnection. Retry or revoke access at your provider.'
                  );
                } finally {
                  setBusy(false);
                }
              }}
            >
              Disconnect AT account
            </button>
          </section>
          <form
            className="surface-card space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void publish();
            }}
          >
            <h2 className="section-title">Compose a public Bluesky post</h2>
            {passage && (
              <p>
                <a
                  className="action-link break-all"
                  href={passage}
                  target="_blank"
                  rel="noreferrer"
                >
                  Review the passage attached to this post
                </a>
              </p>
            )}
            <label className="block">
              Post text
              <textarea
                className="form-control mt-2 min-h-36"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                disabled={Boolean(attempt)}
                required
                maxLength={3000}
              />
            </label>
            <p className="text-sm text-muted">
              Up to 300 characters. This post goes to your public AT repository using the standard
              Bluesky post format. Other services may copy or index it; deleting a site discussion
              does not remove this post.
            </p>
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              Publish publicly from the connected AT account, including the attached passage if
              shown.
            </label>
            <button
              className="btn-primary"
              disabled={busy || !consent || !body.trim() || Boolean(postUrl)}
            >
              Publish to Bluesky publicly
            </button>
            {postUrl && (
              <p role="status">
                Your provider confirmed the record.{' '}
                <a className="action-link" href={postUrl} target="_blank" rel="noreferrer">
                  View on Bluesky
                </a>
                . AppView indexing may take time.
              </p>
            )}
            {attempt && !postUrl && (
              <a
                className="action-link"
                href={`https://bsky.app/profile/${encodeURIComponent(connection.session.sub)}/post/${attempt.rkey}`}
                target="_blank"
                rel="noreferrer"
              >
                Check whether this attempt appeared
              </a>
            )}
            {(postUrl || attempt) && (
              <button
                type="button"
                className="btn-secondary"
                disabled={busy}
                onClick={() => {
                  if (
                    postUrl ||
                    window.confirm(
                      'Only start another post after checking whether the previous attempt published. Continue?'
                    )
                  ) {
                    setAttempt(undefined);
                    setPostUrl('');
                    setConsent(false);
                    setBody('');
                    setError('');
                  }
                }}
              >
                Start another post
              </button>
            )}
          </form>
        </>
      )}
    </main>
  );
}
