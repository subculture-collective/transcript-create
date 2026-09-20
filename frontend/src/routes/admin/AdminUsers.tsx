import { useCallback, useEffect, useRef, useState } from 'react';
import { HTTPError } from 'ky';
import { api } from '../../services/api';
import { useAuth } from '../../services/auth';
import type { AdminUser, OffsetPageInfo, UserRole } from '../../types/api';

const roles: Array<{ value: UserRole; label: string }> = [
  { value: 'user', label: 'User' },
  { value: 'moderator', label: 'Moderator' },
  { value: 'admin', label: 'Admin' },
];

async function roleFailure(error: unknown) {
  if (error instanceof HTTPError) {
    try {
      const body = (await error.response.clone().json()) as { error?: unknown; message?: unknown };
      if (typeof body.error === 'string') {
        return {
          code: body.error,
          message:
            typeof body.message === 'string' ? body.message : 'The role could not be changed.',
        };
      }
    } catch {
      // Fall through to a stable status message.
    }
    if (error.response.status === 403)
      return { code: 'forbidden', message: 'Admin access is required to change roles.' };
    if (error.response.status === 422)
      return { code: 'validation_error', message: 'Choose User, Moderator, or Admin.' };
    if (error.response.status >= 500)
      return {
        code: 'transient',
        message: 'The role service is temporarily unavailable. Try again.',
      };
  }
  return {
    code: 'unknown',
    message: error instanceof Error ? error.message : 'The role could not be changed.',
  };
}

function roleLabel(role: UserRole) {
  return roles.find((item) => item.value === role)?.label ?? role;
}

export default function AdminUsers() {
  const { user: currentUser, capabilities, refresh, invalidateLocalAuth } = useAuth();
  const canManageRoles = capabilities.includes('admin:access');
  const [items, setItems] = useState<AdminUser[]>([]);
  const [q, setQ] = useState('');
  const [appliedQuery, setAppliedQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [pageInfo, setPageInfo] = useState<OffsetPageInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [compact, setCompact] = useState(
    () => window.matchMedia?.('(max-width: 767px)').matches ?? false
  );
  const requestId = useRef(0);
  const abortController = useRef<AbortController | null>(null);

  const fetchUsers = useCallback(
    async (query: string, pageOffset = offset) => {
      abortController.current?.abort();
      const controller = new AbortController();
      abortController.current = controller;
      const currentRequest = ++requestId.current;
      setLoading(true);
      setListError(null);
      setHasLoaded(false);
      setRowErrors({});
      try {
        const response = await api.listAdminUsers(query, controller.signal, pageOffset);
        if (controller.signal.aborted || currentRequest !== requestId.current) return;
        setItems(response.items);
        setPageInfo(response.page_info ?? null);
        setHasLoaded(true);
      } catch (error: unknown) {
        if (controller.signal.aborted || currentRequest !== requestId.current) return;
        const failure = await roleFailure(error);
        if (controller.signal.aborted || currentRequest !== requestId.current) return;
        setListError(
          failure.code === 'forbidden' ? 'Admin access is required to view users.' : failure.message
        );
      } finally {
        if (currentRequest === requestId.current) setLoading(false);
      }
    },
    [offset]
  );

  useEffect(() => {
    void fetchUsers(appliedQuery);
    return () => abortController.current?.abort();
  }, [appliedQuery, offset, fetchUsers]);
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 767px)');
    if (!media) return;
    const change = () => setCompact(media.matches);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);

  async function changeRole(user: AdminUser, nextRole: UserRole) {
    if (!canManageRoles || user.role === nextRole) return;
    setSavingId(user.id);
    setRowErrors((current) => ({ ...current, [user.id]: '' }));
    try {
      const response = await api.updateAdminUserRole(user.id, nextRole);
      setItems((current) =>
        current.map((item) => (item.id === user.id ? { ...item, role: response.role } : item))
      );
      if (currentUser?.id === user.id) {
        // Remove stale admin controls before asking the server for the
        // authoritative capability set. Preserve the session and token while
        // this refresh is in flight so mutations do not fail spuriously.
        invalidateLocalAuth({ preserveUser: true });
        try {
          await refresh();
        } catch {
          // If the role mutation succeeded but auth cannot be revalidated,
          // fail closed rather than leaving stale admin capabilities visible.
          invalidateLocalAuth();
        }
      }
    } catch (error: unknown) {
      const failure = await roleFailure(error);
      const message =
        failure.code === 'final_admin'
          ? 'The final administrator cannot be demoted.'
          : failure.code === 'forbidden'
            ? 'Your admin access changed; refresh before trying again.'
            : failure.code === 'validation_error'
              ? 'Choose User, Moderator, or Admin.'
              : failure.message;
      setRowErrors((current) => ({ ...current, [user.id]: message }));
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <div className="archive-eyebrow">Administration / people</div>
        <h1 className="page-title mt-4">Users & roles</h1>
        <p className="mt-3 max-w-2xl text-muted">
          Manage durable authorization roles. Plans and entitlements remain separate from access
          roles.
        </p>
      </header>

      <form
        className="surface-card flex flex-col gap-3 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          setOffset(0);
          setItems([]);
          setPageInfo(null);
          setAppliedQuery(q.trim());
        }}
      >
        <div className="min-w-0 flex-1">
          <label className="meta-label" htmlFor="admin-user-search">
            Search by email or name
          </label>
          <input
            id="admin-user-search"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            className="form-control mt-2"
          />
        </div>
        <button className="btn" type="submit" disabled={loading && q.trim() === appliedQuery}>
          {loading ? 'Loading…' : 'Apply search'}
        </button>
      </form>

      {listError && (
        <div className="alert-warning" role="alert">
          {listError}
          <button
            className="btn-secondary ml-3 text-sm"
            type="button"
            onClick={() => void fetchUsers(appliedQuery)}
          >
            Retry
          </button>
        </div>
      )}
      {!canManageRoles && (
        <div className="alert-info" role="status">
          Roles are read-only for this account. Admin access is required to change them.
        </div>
      )}

      <div className="surface-card overflow-hidden p-0">
        {compact && (
          <div className="divide-y divide-border/70">
            {items.map((user) => (
              <article key={user.id} className="space-y-2 p-4">
                <p className="font-semibold text-ink">{user.name || 'Unnamed user'}</p>
                <p className="break-all text-sm text-muted">{user.email || '—'}</p>
                {canManageRoles ? (
                  <label className="block text-sm">
                    Role{' '}
                    <select
                      className="form-control mt-1 w-full"
                      value={user.role ?? 'user'}
                      disabled={savingId === user.id}
                      onChange={(event) => void changeRole(user, event.target.value as UserRole)}
                    >
                      {roles.map((role) => (
                        <option key={role.value} value={role.value}>
                          {role.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <span className="badge-success">{roleLabel(user.role ?? 'user')}</span>
                )}
                {rowErrors[user.id] && (
                  <p className="text-xs text-danger" role="alert">
                    {rowErrors[user.id]}
                  </p>
                )}
                <p className="text-xs text-muted">
                  Created {new Date(user.created_at).toLocaleDateString()}
                </p>
              </article>
            ))}
          </div>
        )}
        {!compact && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <caption className="sr-only">Archive users and authorization roles</caption>
              <thead className="border-b border-border bg-surface-muted/70 text-xs uppercase tracking-[0.16em] text-subtle">
                <tr>
                  <th className="px-4 py-3 font-semibold">User</th>
                  <th className="px-4 py-3 font-semibold">Email</th>
                  <th className="px-4 py-3 font-semibold">Role</th>
                  <th className="px-4 py-3 font-semibold">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/70">
                {items.map((user) => (
                  <tr key={user.id} className="align-top hover:bg-surface-muted/35">
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-3">
                        {user.avatar_url && (
                          <img
                            src={user.avatar_url}
                            alt=""
                            className="h-9 w-9 rounded-full border border-border object-cover"
                          />
                        )}
                        <div className="min-w-0">
                          <p className="font-semibold text-ink">{user.name || 'Unnamed user'}</p>
                          <p
                            className="mt-1 max-w-[14rem] truncate font-mono text-[10px] text-subtle"
                            title={user.id}
                          >
                            {user.id}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="max-w-[18rem] px-4 py-4 text-muted">{user.email || '—'}</td>
                    <td className="px-4 py-4">
                      {canManageRoles ? (
                        <div className="min-w-36">
                          <label className="sr-only" htmlFor={`role-${user.id}`}>
                            Role for {user.name || user.email || 'user'}
                          </label>
                          <select
                            id={`role-${user.id}`}
                            className="form-control min-h-10 py-1.5 text-sm"
                            value={user.role ?? 'user'}
                            disabled={savingId === user.id}
                            onChange={(event) =>
                              void changeRole(user, event.target.value as UserRole)
                            }
                          >
                            {roles.map((role) => (
                              <option key={role.value} value={role.value}>
                                {role.label}
                              </option>
                            ))}
                          </select>
                          {rowErrors[user.id] && (
                            <p className="mt-2 max-w-48 text-xs text-danger" role="alert">
                              {rowErrors[user.id]}
                            </p>
                          )}
                        </div>
                      ) : (
                        <span className="badge-success">{roleLabel(user.role ?? 'user')}</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-muted">
                      {new Date(user.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && hasLoaded && !listError && items.length === 0 && (
          <p className="px-4 py-10 text-center text-sm text-muted">No users match this search.</p>
        )}
      </div>
      {hasLoaded && !listError && pageInfo && (
        <nav aria-label="User pages" className="flex items-center gap-3">
          <span className="text-sm text-muted">
            Showing {pageInfo.offset + 1}–{pageInfo.offset + items.length}
          </span>
          <button
            className="btn-secondary"
            type="button"
            disabled={loading || !pageInfo.has_previous_page}
            onClick={() => pageInfo.previous_offset != null && setOffset(pageInfo.previous_offset)}
          >
            Previous
          </button>
          <button
            className="btn-secondary"
            type="button"
            disabled={loading || !pageInfo.has_next_page}
            onClick={() => pageInfo.next_offset != null && setOffset(pageInfo.next_offset)}
          >
            Next
          </button>
        </nav>
      )}
    </div>
  );
}
