import { useEffect, useMemo, useRef, useState } from 'react';
import { HTTPError } from 'ky';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { useAuth } from '../services/auth';
import type {
  AccountResponse,
  ActiveSession,
  LinkedIdentity,
  OAuthProvider,
  UserRole,
} from '../types/api';

const providers: Array<{ id: OAuthProvider; label: string; description: string }> = [
  { id: 'google', label: 'Google', description: 'Use your Google identity to sign in.' },
  { id: 'twitch', label: 'Twitch', description: 'Use your Twitch identity to sign in.' },
];

const roleLabels: Record<UserRole, string> = {
  user: 'User',
  moderator: 'Moderator',
  admin: 'Admin',
};

function formatDate(value?: string | null) {
  if (!value) return 'Not available';
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? 'Not available'
    : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function isAbsoluteHttpsUrl(value: string) {
  if (!value || /\s/.test(value)) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && Boolean(url.hostname);
  } catch {
    return false;
  }
}

type ProfileField = 'name' | 'avatar_url';
type ProfileFieldErrors = Partial<Record<ProfileField, string>>;

type ApiFailure = {
  code: string;
  message: string;
  fieldErrors: ProfileFieldErrors;
};

function parseProfileFieldErrors(details: unknown): ProfileFieldErrors {
  if (!details || typeof details !== 'object' || !('errors' in details)) return {};
  const errors = details.errors;
  if (!Array.isArray(errors)) return {};

  const fieldErrors: ProfileFieldErrors = {};
  for (const item of errors) {
    if (!item || typeof item !== 'object') continue;
    const record = item as { field?: unknown; message?: unknown };
    const field = record.field;
    const message = record.message;
    if (
      (field === 'name' || field === 'avatar_url') &&
      typeof message === 'string' &&
      message.trim()
    ) {
      fieldErrors[field] ??= message;
    }
  }
  return fieldErrors;
}

async function apiFailure(error: unknown, fallback: string) {
  if (error instanceof HTTPError) {
    try {
      const body = (await error.response.clone().json()) as {
        error?: unknown;
        message?: unknown;
        details?: unknown;
      };
      if (typeof body.error === 'string') {
        return {
          code: body.error,
          message: typeof body.message === 'string' ? body.message : fallback,
          fieldErrors: parseProfileFieldErrors(body.details),
        };
      }
    } catch {
      // Use the stable status fallback when the response is not JSON.
    }
    if (error.response.status === 403)
      return {
        code: 'forbidden',
        message: 'You no longer have permission to do that.',
        fieldErrors: {},
      };
    if (error.response.status === 422)
      return { code: 'validation_error', message: fallback, fieldErrors: {} };
    if (error.response.status >= 500)
      return { code: 'transient', message: fallback, fieldErrors: {} };
  }
  return {
    code: 'unknown',
    message: error instanceof Error ? error.message : fallback,
    fieldErrors: {},
  };
}

function ProviderMark({ provider }: { provider: OAuthProvider }) {
  return (
    <span
      aria-hidden="true"
      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border text-sm font-bold ${
        provider === 'google'
          ? 'border-[#4285f4]/40 bg-[#4285f4]/10 text-[#8ab4f8]'
          : 'border-[#9146ff]/40 bg-[#9146ff]/10 text-[#bf94ff]'
      }`}
    >
      {provider === 'google' ? 'G' : 'T'}
    </span>
  );
}

function SessionRow({
  session,
  onRevoke,
  disabled,
}: {
  session: ActiveSession;
  onRevoke: (session: ActiveSession) => void;
  disabled: boolean;
}) {
  return (
    <li className="flex flex-col gap-3 border-b border-border/70 py-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold text-ink">{session.user_agent || 'Unknown device'}</p>
          {session.current && <span className="badge-success">Current session</span>}
        </div>
        <p className="mt-1 text-sm text-muted">
          Last seen {formatDate(session.last_seen_at)} · Started {formatDate(session.created_at)}
        </p>
        <p className="mt-1 text-xs text-subtle">Expires {formatDate(session.expires_at)}</p>
      </div>
      <button
        className="btn-secondary shrink-0 self-start text-sm sm:self-center"
        type="button"
        disabled={disabled}
        onClick={() => onRevoke(session)}
      >
        {session.current ? 'Sign out this session' : 'Revoke'}
      </button>
    </li>
  );
}

export default function AccountPage() {
  const { user, status, error, refresh, invalidateLocalAuth, linkProvider, mergeProvider } =
    useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [profileName, setProfileName] = useState('');
  const [profileAvatar, setProfileAvatar] = useState('');
  const [profileNameError, setProfileNameError] = useState<string | null>(null);
  const [profileAvatarError, setProfileAvatarError] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [providerBusy, setProviderBusy] = useState<OAuthProvider | null>(null);
  const [unlinkPending, setUnlinkPending] = useState<OAuthProvider | null>(null);
  const [mergePending, setMergePending] = useState<OAuthProvider | null>(null);
  const [sessionBusy, setSessionBusy] = useState<string | 'others' | 'all' | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const redirectingAfterDeletion = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const linked = params.get('linked');
    const merged = params.get('merged');
    const error = params.get('error');
    const provider = params.get('provider');
    if (linked) setNotice(`${linked[0]?.toUpperCase() ?? linked} identity linked successfully.`);
    if (merged)
      setNotice(`${merged[0]?.toUpperCase() ?? merged} linked and the accounts were merged.`);
    if (error === 'identity_conflict' && (provider === 'google' || provider === 'twitch')) {
      setMergePending(provider);
      setNotice(
        `That ${provider[0].toUpperCase()}${provider.slice(1)} identity belongs to another HasanAra account. You can merge it into this account after confirming ownership again.`
      );
    }
    if (error === 'account_merge_conflict') {
      setNotice('Those accounts could not be merged safely. Nothing was changed.');
    }
    if (linked || merged || error) navigate(location.pathname, { replace: true });
  }, [location.pathname, location.search, navigate]);

  useEffect(() => {
    if (status === 'loading') return;
    if (!user) {
      if (status === 'anonymous' && !redirectingAfterDeletion.current) {
        navigate('/login?next=%2Faccount', { replace: true });
      }
      return;
    }

    let active = true;
    setLoading(true);
    void api
      .getAccount()
      .then((response) => {
        if (!active) return;
        setAccount(response);
        setProfileName(response.user.name ?? '');
        setProfileAvatar(response.user.avatar_url ?? '');
        setPageError(null);
      })
      .catch(async (error: unknown) => {
        if (!active) return;
        setPageError((await apiFailure(error, 'Your account could not be loaded.')).message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [navigate, status, user]);

  const identityByProvider = useMemo(() => {
    const identities = account?.identities ?? [];
    return new Map(identities.map((identity) => [identity.provider, identity]));
  }, [account?.identities]);

  if (status === 'loading' || (user && loading)) {
    return (
      <div className="py-16 text-center text-muted" role="status">
        Loading account settings…
      </div>
    );
  }

  if (status === 'error' && !user) {
    return (
      <section className="mx-auto max-w-2xl space-y-4 py-10" role="alert">
        <div className="archive-eyebrow">Session check interrupted</div>
        <h1 className="page-title">Could not verify your session</h1>
        <p className="text-muted">
          {error ?? 'We could not determine whether you are signed in.'} Try again to continue.
        </p>
        <button className="btn" type="button" onClick={() => void refresh().catch(() => undefined)}>
          Try again
        </button>
      </section>
    );
  }

  if (!user) {
    return (
      <div className="py-16 text-center text-muted" role="status">
        Redirecting to sign in…
      </div>
    );
  }

  if (pageError || !account) {
    return (
      <section className="mx-auto max-w-2xl space-y-4 py-10" role="alert">
        <div className="archive-eyebrow">Account unavailable</div>
        <h1 className="page-title">Could not open settings</h1>
        <p className="text-muted">{pageError ?? 'The account response was incomplete.'}</p>
        <button className="btn" type="button" onClick={() => window.location.reload()}>
          Try again
        </button>
      </section>
    );
  }

  const role = account.user.role ?? 'user';
  const identityCount = account.identities.length;

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = profileName.trim();
    const avatar = profileAvatar.trim();
    setProfileNameError(null);
    setProfileAvatarError(null);
    setProfileError(null);
    if (name.length < 1 || name.length > 100) {
      setProfileNameError('Display name must be between 1 and 100 characters.');
      return;
    }
    if (avatar && !isAbsoluteHttpsUrl(avatar)) {
      setProfileAvatarError('Avatar URL must be an absolute HTTPS URL, or empty.');
      return;
    }
    setProfileSaving(true);
    try {
      const response = await api.updateProfile({ name, avatar_url: avatar || null });
      setAccount((current) => (current ? { ...current, user: response.user } : current));
      await refresh();
      setNotice('Profile saved.');
    } catch (error: unknown) {
      const failure: ApiFailure = await apiFailure(error, 'Your profile could not be saved.');
      setProfileNameError(failure.fieldErrors.name ?? null);
      setProfileAvatarError(failure.fieldErrors.avatar_url ?? null);
      setProfileError(Object.keys(failure.fieldErrors).length > 0 ? null : failure.message);
    } finally {
      setProfileSaving(false);
    }
  }

  async function startLink(provider: OAuthProvider) {
    setProviderBusy(provider);
    setNotice(null);
    try {
      await linkProvider(provider);
    } catch (error: unknown) {
      setNotice((await apiFailure(error, 'The provider link could not be started.')).message);
      setProviderBusy(null);
    }
  }

  async function startMerge(provider: OAuthProvider) {
    setProviderBusy(provider);
    setNotice(null);
    try {
      await mergeProvider(provider);
    } catch (error: unknown) {
      setNotice((await apiFailure(error, 'The account merge could not be started.')).message);
      setProviderBusy(null);
    }
  }

  async function unlinkProvider(provider: OAuthProvider) {
    if (unlinkPending !== provider) {
      setUnlinkPending(provider);
      return;
    }
    setProviderBusy(provider);
    setUnlinkPending(null);
    setNotice(null);
    try {
      await api.unlinkProvider(provider);
      const response = await api.getAccount();
      setAccount(response);
      setNotice(`${provider[0]?.toUpperCase() ?? provider} identity unlinked.`);
    } catch (error: unknown) {
      const failure = await apiFailure(error, 'The identity could not be unlinked.');
      setNotice(
        failure.code === 'last_identity'
          ? 'Your last sign-in identity must stay linked.'
          : failure.message
      );
    } finally {
      setProviderBusy(null);
    }
  }

  async function revoke(session: ActiveSession) {
    setSessionBusy(session.id);
    setSessionMessage(null);
    try {
      await api.revokeSession(session.id);
      if (session.current) {
        invalidateLocalAuth();
        navigate('/', { replace: true });
        return;
      }
      setAccount(await api.getAccount());
      setSessionMessage('Session revoked.');
    } catch (error: unknown) {
      setSessionMessage((await apiFailure(error, 'That session could not be revoked.')).message);
    } finally {
      setSessionBusy(null);
    }
  }

  async function revokeOtherSessions() {
    setSessionBusy('others');
    setSessionMessage(null);
    try {
      const response = await api.revokeSessions(true);
      setAccount(await api.getAccount());
      setSessionMessage(
        `${response.revoked} other session${response.revoked === 1 ? '' : 's'} logged out.`
      );
    } catch (error: unknown) {
      setSessionMessage(
        (await apiFailure(error, 'Other sessions could not be logged out.')).message
      );
    } finally {
      setSessionBusy(null);
    }
  }

  async function revokeAllSessions() {
    setSessionBusy('all');
    setSessionMessage(null);
    try {
      await api.revokeSessions(false);
      invalidateLocalAuth();
      navigate('/', { replace: true });
    } catch (error: unknown) {
      setSessionMessage((await apiFailure(error, 'All sessions could not be logged out.')).message);
      setSessionBusy(null);
    }
  }

  async function deleteAccount(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (deleteConfirmation !== 'DELETE') return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await api.deleteAccount();
      // Clear local auth before navigating. This also invalidates any in-flight
      // refresh so it cannot restore a deleted account.
      redirectingAfterDeletion.current = true;
      invalidateLocalAuth();
      navigate('/', { replace: true });
    } catch (error: unknown) {
      const failure = await apiFailure(
        error,
        'Your account could not be deleted. Nothing was changed.'
      );
      setDeleteError(
        failure.code === 'final_admin'
          ? 'The final administrator account cannot be deleted.'
          : failure.message
      );
      setDeleteBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-7">
      <header className="archive-masthead px-6 py-8 sm:px-9 sm:py-10">
        <div className="relative z-10 max-w-3xl">
          <div className="archive-eyebrow">Account / settings</div>
          <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h1 className="page-title">Your account, in order.</h1>
              <p className="mt-4 max-w-2xl text-lg leading-7 text-muted">
                Keep your profile current, choose how you sign in, and see where your archive
                account is active.
              </p>
            </div>
            <span className="badge-success shrink-0 self-start sm:self-end">
              {roleLabels[role]}
            </span>
          </div>
        </div>
      </header>

      {notice && (
        <div className="alert-success" role="status" aria-live="polite">
          {notice}
        </div>
      )}

      {mergePending && (
        <section
          className="archive-section border-warning/40"
          role="alertdialog"
          aria-labelledby="merge-account-heading"
          aria-describedby="merge-account-description"
        >
          <div className="archive-eyebrow">Account merge</div>
          <h2 id="merge-account-heading" className="mt-3 text-xl font-semibold text-ink">
            Merge and link {mergePending === 'google' ? 'Google' : 'Twitch'}?
          </h2>
          <p id="merge-account-description" className="mt-3 max-w-3xl text-sm leading-6 text-muted">
            This signed-in account will be kept. Saved moments, searches, vocabularies, and job
            ownership from the other account will move here. Other sessions and API keys from the
            absorbed account will be revoked. This cannot be undone.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn"
              disabled={providerBusy === mergePending}
              onClick={() => void startMerge(mergePending)}
            >
              {providerBusy === mergePending
                ? 'Opening…'
                : `Merge and link ${mergePending === 'google' ? 'Google' : 'Twitch'}`}
            </button>
            <button
              type="button"
              className="btn-ghost"
              disabled={providerBusy === mergePending}
              onClick={() => setMergePending(null)}
            >
              Cancel
            </button>
          </div>
        </section>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="archive-section" aria-labelledby="profile-heading">
          <div className="archive-rule-title">
            <h2 id="profile-heading">Profile</h2>
          </div>
          <p className="mt-4 text-sm text-muted">
            This is the name and avatar shown around HasanAra.
          </p>
          <form className="mt-6 space-y-5" onSubmit={saveProfile}>
            <div>
              <label className="meta-label" htmlFor="account-name">
                Display name
              </label>
              <input
                id="account-name"
                className="form-control mt-2"
                value={profileName}
                maxLength={100}
                onChange={(event) => setProfileName(event.target.value)}
                aria-describedby={`account-name-help${profileNameError ? ' account-name-error' : ''}`}
                aria-invalid={Boolean(profileNameError)}
              />
              <p id="account-name-help" className="mt-2 text-xs text-subtle">
                1–100 characters.
              </p>
              {profileNameError && (
                <p id="account-name-error" className="mt-2 text-sm text-danger" role="alert">
                  {profileNameError}
                </p>
              )}
            </div>
            <div>
              <label className="meta-label" htmlFor="account-avatar">
                Avatar URL <span className="normal-case tracking-normal">(optional)</span>
              </label>
              <input
                id="account-avatar"
                type="text"
                inputMode="url"
                className="form-control mt-2"
                value={profileAvatar}
                placeholder="https://…"
                onChange={(event) => setProfileAvatar(event.target.value)}
                aria-describedby={`account-avatar-help${profileAvatarError ? ' account-avatar-error' : ''}`}
                aria-invalid={Boolean(profileAvatarError)}
              />
              <p id="account-avatar-help" className="mt-2 text-xs text-subtle">
                HTTPS images only. Leave empty to remove it.
              </p>
              {profileAvatarError && (
                <p id="account-avatar-error" className="mt-2 text-sm text-danger" role="alert">
                  {profileAvatarError}
                </p>
              )}
            </div>
            {profileError && (
              <p id="profile-error" className="text-sm text-danger" role="alert">
                {profileError}
              </p>
            )}
            <button className="btn" type="submit" disabled={profileSaving}>
              {profileSaving ? 'Saving…' : 'Save profile'}
            </button>
          </form>
        </section>

        <section className="archive-section" aria-labelledby="identities-heading">
          <div className="archive-rule-title">
            <h2 id="identities-heading">Linked sign-ins</h2>
          </div>
          <p className="mt-4 text-sm text-muted">
            Link both providers for a reliable way back into your account.
          </p>
          <div className="mt-5 divide-y divide-border/70">
            {providers.map((provider) => {
              const identity: LinkedIdentity | undefined = identityByProvider.get(provider.id);
              const pending = unlinkPending === provider.id;
              return (
                <div
                  className="flex flex-col gap-4 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between"
                  key={provider.id}
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <ProviderMark provider={provider.id} />
                    <div className="min-w-0">
                      <p className="font-semibold text-ink">{provider.label}</p>
                      {identity ? (
                        <>
                          <p className="mt-1 text-sm text-success">Connected</p>
                          <p className="mt-1 truncate text-xs text-muted">
                            {identity.email || identity.name || provider.description}
                          </p>
                          <p className="mt-1 text-xs text-subtle">
                            Last used {formatDate(identity.last_login_at)}
                          </p>
                        </>
                      ) : (
                        <p className="mt-1 text-sm text-muted">{provider.description}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2 sm:justify-end">
                    {identity ? (
                      <>
                        {pending && (
                          <span className="self-center text-xs text-warning">
                            Unlink {provider.label}?
                          </span>
                        )}
                        {identityCount <= 1 && (
                          <span
                            id={`unlink-help-${provider.id}`}
                            className="self-center max-w-52 text-xs text-subtle"
                          >
                            Keep at least one sign-in identity linked.
                          </span>
                        )}
                        <button
                          className={pending ? 'btn-secondary text-sm' : 'btn-ghost text-sm'}
                          type="button"
                          disabled={identityCount <= 1 || providerBusy === provider.id}
                          onClick={() => void unlinkProvider(provider.id)}
                          aria-describedby={
                            identityCount <= 1 ? `unlink-help-${provider.id}` : undefined
                          }
                        >
                          {providerBusy === provider.id
                            ? 'Working…'
                            : pending
                              ? 'Confirm unlink'
                              : 'Unlink'}
                        </button>
                        {pending && (
                          <button
                            className="btn-ghost text-sm"
                            type="button"
                            onClick={() => setUnlinkPending(null)}
                          >
                            Cancel
                          </button>
                        )}
                      </>
                    ) : (
                      <button
                        className="btn-secondary text-sm"
                        type="button"
                        disabled={providerBusy === provider.id}
                        onClick={() => void startLink(provider.id)}
                      >
                        {providerBusy === provider.id ? 'Opening…' : `Link ${provider.label}`}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="mt-5 border-t border-border/70 pt-4 text-xs text-subtle">
            Provider emails are shown only as account metadata. Provider IDs and tokens are never
            displayed.
          </p>
        </section>
      </div>

      <section className="archive-section" aria-labelledby="sessions-heading">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="archive-rule-title">
              <h2 id="sessions-heading">Active sessions</h2>
            </div>
            <p className="mt-4 text-sm text-muted">
              Review recent access and end sessions you no longer recognize.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {account.sessions.some((session) => !session.current) && (
              <button
                className="btn-secondary text-sm"
                type="button"
                disabled={sessionBusy !== null}
                onClick={() => void revokeOtherSessions()}
              >
                {sessionBusy === 'others' ? 'Logging out…' : 'Log out other sessions'}
              </button>
            )}
            <button
              className="btn-ghost text-sm"
              type="button"
              disabled={sessionBusy !== null}
              onClick={() => void revokeAllSessions()}
            >
              {sessionBusy === 'all' ? 'Logging out…' : 'Log out all sessions'}
            </button>
          </div>
        </div>
        {sessionMessage && (
          <p className="mt-4 text-sm text-muted" role="status" aria-live="polite">
            {sessionMessage}
          </p>
        )}
        <ul className="mt-4" aria-label="Active sessions">
          {account.sessions.map((session) => (
            <SessionRow
              key={session.id}
              session={session}
              onRevoke={(item) => void revoke(item)}
              disabled={sessionBusy !== null}
            />
          ))}
        </ul>
        {account.sessions.length === 0 && (
          <p className="py-6 text-sm text-muted">No active sessions were returned.</p>
        )}
      </section>

      <section
        className="rounded-2xl border border-danger/35 bg-danger-soft/45 p-5 sm:p-6"
        aria-labelledby="danger-heading"
      >
        <div className="archive-rule-title text-danger">
          <h2 id="danger-heading">Danger zone</h2>
        </div>
        <div className="mt-4 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <h2 className="text-lg font-semibold text-ink">Delete this account</h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              This permanently removes your account and private data, revokes access, and cannot be
              undone. Public archive records are not deleted.
            </p>
          </div>
          {!deleteOpen && (
            <button
              className="btn-secondary border-danger/50 text-danger hover:border-danger hover:bg-danger/10"
              type="button"
              onClick={() => setDeleteOpen(true)}
            >
              Delete account
            </button>
          )}
        </div>
        {deleteOpen && (
          <form className="mt-5 max-w-xl border-t border-danger/25 pt-5" onSubmit={deleteAccount}>
            <label className="meta-label text-danger" htmlFor="delete-confirmation">
              Type DELETE to confirm account deletion
            </label>
            <input
              id="delete-confirmation"
              className="form-control mt-2 border-danger/40 focus:border-danger focus:ring-danger/25"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              aria-describedby="delete-help"
            />
            <p id="delete-help" className="mt-2 text-xs text-subtle">
              Confirmation is case-sensitive.
            </p>
            {deleteError && (
              <p className="mt-3 text-sm text-danger" role="alert">
                {deleteError}
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                className="btn-secondary border-danger/50 text-danger hover:border-danger hover:bg-danger/10"
                type="submit"
                disabled={deleteConfirmation !== 'DELETE' || deleteBusy}
              >
                {deleteBusy ? 'Deleting…' : 'Confirm deletion'}
              </button>
              <button
                className="btn-ghost"
                type="button"
                disabled={deleteBusy}
                onClick={() => {
                  setDeleteOpen(false);
                  setDeleteConfirmation('');
                  setDeleteError(null);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
