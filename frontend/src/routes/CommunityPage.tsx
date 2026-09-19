import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../services';
import { useSite } from '../services/site';
import {
  community,
  type CommunityPost,
  type CommunityReport,
  type PostPage,
} from '../services/community';
import { buildPassageLink, formatPassageTime } from '../features/passages/range';

function PostCard({ post, refresh }: { post: CommunityPost; refresh: () => void }) {
  const { user, role } = useAuth();
  const [replies, setReplies] = useState<PostPage | null>(null);
  const [body, setBody] = useState('');
  const [reason, setReason] = useState('');
  const [tools, setTools] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const moderator = role === 'admin' || role === 'moderator';
  async function act(task: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage('');
    try {
      await task();
      setMessage(success);
      refresh();
    } catch {
      setMessage('That action failed. Your text is preserved; please retry.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <article
      className="surface-card p-5 space-y-3"
      aria-label={`${post.kind} by ${post.author_name}`}
    >
      <div className="flex flex-wrap justify-between gap-2 text-sm text-muted">
        <strong>{post.author_name}</strong>
        <span>
          {post.pinned ? 'Pinned · ' : ''}
          {post.kind} · {post.status !== 'published' ? `${post.status} · ` : ''}
          <time dateTime={post.created_at}>{new Date(post.created_at).toLocaleString()}</time>
        </span>
      </div>
      <p className="whitespace-pre-wrap break-words">{post.body}</p>
      {post.video_id && post.start_ms !== null && post.end_ms !== null && (
        <Link
          className="text-accent underline"
          to={buildPassageLink(post.video_id, { startMs: post.start_ms, endMs: post.end_ms })}
        >
          Watch in context: {post.video_title} · {formatPassageTime(post.start_ms)}–
          {formatPassageTime(post.end_ms)}
        </Link>
      )}
      <div className="flex flex-wrap gap-2">
        {!post.parent_id && post.status === 'published' && (
          <button
            className="btn-secondary"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                setReplies(await community.posts(0, post.id));
              }, 'Discussion opened.')
            }
          >
            Open discussion
          </button>
        )}
        {user?.id === post.author_id && post.status === 'draft' && (
          <button
            className="btn-primary"
            disabled={busy}
            onClick={() => void act(() => community.publish(post.id), 'Published publicly.')}
          >
            Publish publicly
          </button>
        )}
        {user && (
          <button className="btn-ghost" onClick={() => setTools(!tools)}>
            Post actions
          </button>
        )}
      </div>
      {tools && (
        <div className="space-y-3 border-t border-border pt-3">
          <label className="block">
            Reason for report or moderation
            <input
              className="form-control w-full"
              value={reason}
              maxLength={1000}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {post.status === 'published' && (
              <button
                className="btn-secondary"
                disabled={busy || !reason.trim()}
                onClick={() =>
                  void act(
                    () => community.report(post.id, reason),
                    'Report submitted privately to site moderators.'
                  )
                }
              >
                Report
              </button>
            )}
            {moderator && post.status !== 'draft' && (
              <button
                className="btn-secondary"
                disabled={busy || !reason.trim()}
                onClick={() =>
                  void act(
                    () =>
                      community.moderate(
                        post.id,
                        post.status === 'hidden' ? 'restore' : 'hide',
                        reason
                      ),
                    'Moderation saved.'
                  )
                }
              >
                {post.status === 'hidden' ? 'Restore' : 'Hide'}
              </button>
            )}
            {role === 'admin' && !post.parent_id && post.status !== 'draft' && (
              <button
                className="btn-secondary"
                disabled={busy || !reason.trim()}
                onClick={() =>
                  void act(
                    () => community.moderate(post.id, post.pinned ? 'unpin' : 'pin', reason),
                    'Pin updated.'
                  )
                }
              >
                {post.pinned ? 'Unpin' : 'Pin'}
              </button>
            )}
            {user?.id === post.author_id && (
              <button
                className="btn-ghost text-danger"
                disabled={busy}
                onClick={() => {
                  if (
                    window.confirm(
                      'Delete this post permanently? Its replies will also be deleted.'
                    )
                  )
                    void act(() => community.remove(post.id), 'Deleted.');
                }}
              >
                Delete post and replies
              </button>
            )}
          </div>
        </div>
      )}
      {replies && (
        <section
          className="space-y-3 border-l-2 border-accent pl-3"
          aria-label="Discussion replies"
        >
          {replies.items.length === 0 && <p className="text-muted">No replies yet.</p>}
          {replies.items.map((reply) => (
            <PostCard
              key={reply.id}
              post={reply}
              refresh={() => {
                void community
                  .posts(0, post.id)
                  .then(setReplies)
                  .catch(() => setMessage('Could not refresh replies.'));
              }}
            />
          ))}
          {replies.next_offset !== null && (
            <button
              className="btn-secondary"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const next = await community.posts(replies.next_offset!, post.id);
                  setReplies({
                    items: [...replies.items, ...next.items],
                    next_offset: next.next_offset,
                  });
                }, 'More replies loaded.')
              }
            >
              More replies
            </button>
          )}
          {user ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void act(async () => {
                  await community.create({
                    kind: 'reply',
                    body,
                    parent_id: post.id,
                    publish: true,
                  });
                  setBody('');
                  setReplies(await community.posts(0, post.id));
                }, 'Reply published publicly.');
              }}
            >
              <label className="block">
                Reply publicly
                <textarea
                  className="form-control w-full"
                  required
                  maxLength={5000}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                />
              </label>
              <button className="btn-primary mt-2" disabled={busy || !body.trim()}>
                Publish reply publicly
              </button>
            </form>
          ) : (
            <Link to="/login" className="text-accent">
              Sign in to reply
            </Link>
          )}
        </section>
      )}
      {message && (
        <p role="status" className="text-sm text-muted">
          {message}
        </p>
      )}
    </article>
  );
}

export default function CommunityPage() {
  const site = useSite();
  const { user, role } = useAuth();
  const [params] = useSearchParams();
  const [tab, setTab] = useState<'feed' | 'mine' | 'reports' | 'hidden'>('feed');
  const [page, setPage] = useState<PostPage>({ items: [], next_offset: null });
  const [reports, setReports] = useState<CommunityReport[]>([]);
  const [reportsNext, setReportsNext] = useState<number | null>(null);
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const videoId = params.get('video_id');
  const start = Number(params.get('start_ms'));
  const end = Number(params.get('end_ms'));
  const passage =
    videoId &&
    /^[0-9a-f-]{36}$/i.test(videoId) &&
    params.has('start_ms') &&
    params.has('end_ms') &&
    Number.isSafeInteger(start) &&
    start >= 0 &&
    Number.isSafeInteger(end) &&
    end > start;
  const refresh = useCallback(async () => {
    if (!site.community_enabled) return;
    setLoading(true);
    setError('');
    try {
      if (tab === 'reports') {
        const next = await community.reports();
        setReports(next.items);
        setReportsNext(next.next_offset);
      } else
        setPage(
          await (tab === 'mine'
            ? community.mine()
            : tab === 'hidden'
              ? community.hidden()
              : community.posts())
        );
    } catch {
      setError('Could not load the community. Please retry.');
    } finally {
      setLoading(false);
    }
  }, [site.community_enabled, tab]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  async function submit(publish: boolean) {
    setBusy(true);
    setError('');
    try {
      await community.create({
        kind: passage ? 'discussion' : 'update',
        body,
        publish,
        ...(passage ? { video_id: videoId!, start_ms: start, end_ms: end } : {}),
      });
      setBody('');
      setNotice(
        publish ? 'Published publicly on this site.' : 'Draft saved. Find it under My posts.'
      );
      await refresh();
    } catch {
      setError('Could not save the post. Your text is preserved; check your access and retry.');
    } finally {
      setBusy(false);
    }
  }
  async function exportOwn() {
    setBusy(true);
    setError('');
    try {
      const data = await community.export();
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      );
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'community-posts.json';
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(
        'Your posts were exported. Reports and other members’ private content are excluded.'
      );
    } catch {
      setError('Export failed. Please retry.');
    } finally {
      setBusy(false);
    }
  }
  if (!site.community_enabled)
    return (
      <div className="surface-card p-6">
        <h1>Community</h1>
        <p>Community is not enabled on this archive.</p>
        <Link to="/search">Explore the archive</Link>
      </div>
    );
  return (
    <div className="mx-auto max-w-3xl space-y-6 py-6">
      <header>
        {site.atproto_enabled && (
          <a className="action-link" href="/at.html">
            Connect an AT account for public sharing
          </a>
        )}
        <p className="text-sm uppercase tracking-wider text-accent">
          {site.creator_name} · Community
        </p>
        <h1 className="text-3xl font-bold mt-2">Updates and conversations</h1>
        <p className="mt-2 text-muted">
          Follow creator updates and discuss passages with their source in view. Posts are public;
          reports go privately to site moderators.
        </p>
        <Link className="text-accent underline" to="/timeline">
          Browse the archive timeline
        </Link>
      </header>
      {user && (role === 'admin' || passage) && (
        <section className="surface-card p-5 space-y-3" aria-label="Write a post">
          <h2 className="text-xl font-semibold">
            {passage ? 'Discuss this passage' : 'Creator update'}
          </h2>
          {passage && (
            <Link
              className="text-accent underline"
              to={buildPassageLink(videoId!, { startMs: start, endMs: end })}
            >
              Review source · {formatPassageTime(start)}–{formatPassageTime(end)}
            </Link>
          )}
          <label className="block">
            Post text
            <textarea
              className="form-control w-full min-h-32"
              maxLength={5000}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </label>
          <p className="text-sm text-muted">
            {body.length}/5000 · Publishing makes this text visible to everyone on this site.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              className="btn-secondary"
              disabled={busy || !body.trim()}
              onClick={() => void submit(false)}
            >
              Save draft
            </button>
            <button
              className="btn-primary"
              disabled={busy || !body.trim()}
              onClick={() => void submit(true)}
            >
              Publish publicly
            </button>
          </div>
        </section>
      )}
      {!user && (
        <p>
          <Link className="text-accent underline" to="/login">
            Sign in
          </Link>{' '}
          to discuss a passage or reply.
        </p>
      )}
      {user && role !== 'admin' && !passage && (
        <p className="text-muted">
          To start a discussion, select a passage in a transcript and choose “Discuss passage”.
        </p>
      )}
      <div className="flex flex-wrap gap-2" aria-label="Community views">
        <button
          className={tab === 'feed' ? 'btn-primary' : 'btn-secondary'}
          onClick={() => setTab('feed')}
        >
          Public feed
        </button>
        {user && (
          <>
            <button
              className={tab === 'mine' ? 'btn-primary' : 'btn-secondary'}
              onClick={() => setTab('mine')}
            >
              My posts
            </button>
            <button className="btn-ghost" disabled={busy} onClick={() => void exportOwn()}>
              Export my posts
            </button>
          </>
        )}
        {(role === 'admin' || role === 'moderator') && (
          <>
            <button
              className={tab === 'hidden' ? 'btn-primary' : 'btn-secondary'}
              onClick={() => setTab('hidden')}
            >
              Hidden posts
            </button>
            <button
              className={tab === 'reports' ? 'btn-primary' : 'btn-secondary'}
              onClick={() => setTab('reports')}
            >
              Reports
            </button>
          </>
        )}
      </div>
      {error && (
        <p role="alert">
          {error}{' '}
          <button className="btn-ghost" onClick={() => void refresh()}>
            Retry loading
          </button>
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {loading && page.items.length === 0 && reports.length === 0 ? (
        <p role="status">Loading community…</p>
      ) : tab === 'reports' ? (
        <section aria-label="Moderation reports" className="space-y-4">
          {!reports.length && <p className="surface-card p-6 text-muted">No open reports.</p>}
          {reports.map((report) => (
            <ReportCard key={report.id} report={report} refresh={() => void refresh()} />
          ))}
          {reportsNext !== null && (
            <button
              className="btn-secondary"
              onClick={() => {
                void community
                  .reports(reportsNext)
                  .then((next) => {
                    setReports([...reports, ...next.items]);
                    setReportsNext(next.next_offset);
                  })
                  .catch(() => setError('Could not load more reports.'));
              }}
            >
              More reports
            </button>
          )}
        </section>
      ) : (
        <section aria-label={tab === 'mine' ? 'My posts' : 'Public posts'} className="space-y-4">
          {!page.items.length && !error && (
            <p className="surface-card p-6 text-muted">
              {tab === 'mine'
                ? 'You have not written any posts yet.'
                : 'No public posts yet. Conversations begin with a passage.'}
            </p>
          )}
          {page.items.map((post) => (
            <PostCard key={post.id} post={post} refresh={() => void refresh()} />
          ))}
          {page.next_offset !== null && (
            <button
              className="btn-secondary"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const next = await (tab === 'mine'
                    ? community.mine(page.next_offset!)
                    : tab === 'hidden'
                      ? community.hidden(page.next_offset!)
                      : community.posts(page.next_offset!));
                  setPage({ items: [...page.items, ...next.items], next_offset: next.next_offset });
                } catch {
                  setError('Could not load more posts.');
                } finally {
                  setBusy(false);
                }
              }}
            >
              More posts
            </button>
          )}
        </section>
      )}
    </div>
  );
}

function ReportCard({ report, refresh }: { report: CommunityReport; refresh: () => void }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function handle(action: 'hide' | 'restore' | 'resolve') {
    setBusy(true);
    try {
      if (action === 'resolve') await community.resolve(report.id, reason);
      else await community.moderate(report.post_id, action, reason);
      refresh();
    } catch {
      setError('Could not save moderation. Please retry.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="surface-card p-5 space-y-3">
      <p className="whitespace-pre-wrap break-words">{report.body}</p>
      <p className="text-muted">
        Reported: {report.reason} · {report.post_status}
      </p>
      <label className="block">
        Decision reason
        <input
          className="form-control w-full"
          maxLength={1000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <div className="flex gap-2">
        <button
          className="btn-secondary"
          disabled={busy || !reason.trim()}
          onClick={() => void handle(report.post_status === 'hidden' ? 'restore' : 'hide')}
        >
          {report.post_status === 'hidden' ? 'Restore post' : 'Hide post'}
        </button>
        <button
          className="btn-secondary"
          disabled={busy || !reason.trim()}
          onClick={() => void handle('resolve')}
        >
          Resolve report
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
    </article>
  );
}
