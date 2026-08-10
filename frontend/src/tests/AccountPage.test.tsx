import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axe from 'axe-core';
import AccountPage from '../routes/AccountPage';
import { AuthProvider } from '../services/auth';
import { setCsrfToken } from '../services/api';

const user = {
  id: 'user-1',
  email: 'person@example.com',
  name: 'Archive Person',
  role: 'moderator' as const,
};
const googleIdentity = {
  id: 'identity-google',
  provider: 'google' as const,
  email: 'person@example.com',
  name: 'Archive Person',
  created_at: '2026-01-01T00:00:00Z',
  last_login_at: '2026-01-02T00:00:00Z',
};
const twitchIdentity = {
  id: 'identity-twitch',
  provider: 'twitch' as const,
  email: 'streamer@example.com',
  name: 'Streamer',
  created_at: '2026-01-02T00:00:00Z',
  last_login_at: '2026-01-03T00:00:00Z',
};
const currentSession = {
  id: 'session-current',
  user_agent: 'Current Browser',
  created_at: '2026-01-01T00:00:00Z',
  last_seen_at: '2026-01-03T00:00:00Z',
  expires_at: '2026-02-01T00:00:00Z',
  current: true,
};
const otherSession = {
  id: 'session-other',
  user_agent: 'Other Browser',
  created_at: '2026-01-02T00:00:00Z',
  last_seen_at: '2026-01-03T00:00:00Z',
  expires_at: '2026-02-01T00:00:00Z',
  current: false,
};

type Account = {
  user: typeof user;
  identities: Array<typeof googleIdentity | typeof twitchIdentity>;
  sessions: Array<typeof currentSession | typeof otherSession>;
};

function Location() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

function renderPage(entry = '/account') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AuthProvider>
        <Routes>
          <Route path="/account" element={<AccountPage />} />
          <Route path="/" element={<Location />} />
          <Route path="/login" element={<Location />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function installApi(handler: (request: Request) => Response | Promise<Response>) {
  const fetchMock = vi.fn((request: RequestInfo | URL) =>
    Promise.resolve(handler(request as Request))
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('AccountPage', () => {
  let account: Account;

  beforeEach(() => {
    account = {
      user,
      identities: [googleIdentity, twitchIdentity],
      sessions: [currentSession, otherSession],
    };
    setCsrfToken(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('loads account settings through authenticated Ky requests without rendering sensitive payload fields', async () => {
    installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account'))
        return json({
          ...account,
          identities: [
            {
              ...googleIdentity,
              subject: 'unexpected-provider-subject',
              access_token: 'unexpected-raw-access-token',
              token_hash: 'unexpected-token-hash',
            },
          ],
          sessions: [
            {
              ...currentSession,
              ip_address: '203.0.113.42',
              last_ip: '198.51.100.27',
            },
          ],
        });
      return json({ error: 'unexpected' }, 500);
    });

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Your account, in order.' })).toBeVisible();
    expect(screen.getByText('Moderator')).toBeVisible();
    expect(screen.getByText('Google')).toBeVisible();
    expect(screen.getByText(/^Last used /)).toBeVisible();
    expect(screen.getByText('Current session')).toBeVisible();
    expect(
      screen.queryByText(
        /unexpected-provider-subject|unexpected-raw-access-token|unexpected-token-hash|203\.0\.113\.42|198\.51\.100\.27/i
      )
    ).not.toBeInTheDocument();
  });

  it('uses a page heading followed by section headings', async () => {
    installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account')) return json(account);
      return json({ error: 'unexpected' }, 500);
    });

    const { container } = renderPage();

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Your account, in order.' })
    ).toBeVisible();
    for (const name of ['Profile', 'Linked sign-ins', 'Active sessions', 'Danger zone']) {
      expect(screen.getByRole('heading', { level: 2, name })).toBeVisible();
    }
    expect(screen.getByRole('heading', { level: 2, name: 'Delete this account' })).toBeVisible();
    expect((await axe.run(container)).violations).toEqual([]);
  });

  it('saves a profile with CSRF and preserves inline client and server validation errors', async () => {
    const fetchMock = installApi(async (request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (path.endsWith('/account') && request.method === 'PATCH') {
        expect(request.headers.get('X-CSRF-Token')).toBe('csrf-token');
        const payload = await request.clone().json();
        if (payload.name === 'Server Error')
          return json(
            {
              error: 'validation_error',
              details: {
                errors: [{ field: 'name', message: 'That display name is unavailable.' }],
              },
            },
            422
          );
        expect(payload).toEqual({ name: 'Updated Name', avatar_url: null });
        account = { ...account, user: { ...user, name: 'Updated Name' } };
        return json({ user: account.user });
      }
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { name: 'Your account, in order.' });

    await events.clear(screen.getByLabelText('Display name'));
    await events.type(screen.getByLabelText('Display name'), 'Updated Name');
    await events.clear(screen.getByLabelText(/Avatar URL/));
    await events.click(screen.getByRole('button', { name: 'Save profile' }));
    await screen.findByText('Profile saved.');
    expect(fetchMock.mock.calls.some(([request]) => (request as Request).method === 'PATCH')).toBe(
      true
    );

    await events.clear(screen.getByLabelText('Display name'));
    await events.click(screen.getByRole('button', { name: 'Save profile' }));
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Display name must be between 1 and 100 characters.'
    );
    expect(screen.getByLabelText('Display name')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Display name')).toHaveAttribute(
      'aria-describedby',
      'account-name-help account-name-error'
    );

    await events.type(screen.getByLabelText('Display name'), 'Server Error');
    await events.click(screen.getByRole('button', { name: 'Save profile' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('That display name is unavailable.');
    expect(screen.getByLabelText('Display name')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Display name')).toHaveAttribute(
      'aria-describedby',
      'account-name-help account-name-error'
    );
  });

  it('associates a backend avatar_url validation error only with the avatar field', async () => {
    installApi(async (request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (path.endsWith('/account') && request.method === 'PATCH')
        return json(
          {
            error: 'validation_error',
            details: {
              errors: [{ field: 'avatar_url', message: 'That avatar image is not allowed.' }],
            },
          },
          422
        );
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    const avatar = await screen.findByLabelText(/Avatar URL/);

    await events.type(avatar, 'https://images.example/avatar.png');
    await events.click(screen.getByRole('button', { name: 'Save profile' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('That avatar image is not allowed.');
    expect(screen.getByLabelText('Display name')).toHaveAttribute('aria-invalid', 'false');
    expect(screen.getByLabelText('Display name')).toHaveAttribute(
      'aria-describedby',
      'account-name-help'
    );
    expect(avatar).toHaveAttribute('aria-invalid', 'true');
    expect(avatar).toHaveAttribute('aria-describedby', 'account-avatar-help account-avatar-error');
  });

  it('keeps unknown backend validation errors form-level without invalidating profile fields', async () => {
    installApi(async (request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (path.endsWith('/account') && request.method === 'PATCH')
        return json(
          {
            error: 'validation_error',
            message: 'Your profile could not be saved.',
            details: { errors: [{ field: 'general', message: 'A general validation error.' }] },
          },
          422
        );
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    const avatar = await screen.findByLabelText(/Avatar URL/);

    await events.type(avatar, 'https://images.example/avatar.png');
    await events.click(screen.getByRole('button', { name: 'Save profile' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Your profile could not be saved.');
    expect(screen.getByLabelText('Display name')).toHaveAttribute('aria-invalid', 'false');
    expect(screen.getByLabelText('Display name')).toHaveAttribute(
      'aria-describedby',
      'account-name-help'
    );
    expect(avatar).toHaveAttribute('aria-invalid', 'false');
    expect(avatar).toHaveAttribute('aria-describedby', 'account-avatar-help');
  });

  it('keeps invalid avatar URLs inline and submits a trimmed valid HTTPS URL from the keyboard', async () => {
    const patchBodies: unknown[] = [];
    installApi(async (request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (path.endsWith('/account') && request.method === 'PATCH') {
        patchBodies.push(await request.clone().json());
        return json({ user: { ...user, avatar_url: 'https://images.example/avatar.png' } });
      }
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    const avatar = await screen.findByLabelText(/Avatar URL/);

    for (const value of ['not a URL', 'http://images.example/avatar.png', 'https://']) {
      await events.clear(avatar);
      await events.type(avatar, value);
      await events.click(screen.getByRole('button', { name: 'Save profile' }));
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Avatar URL must be an absolute HTTPS URL, or empty.'
      );
      expect(avatar).toHaveAttribute('aria-invalid', 'true');
      expect(avatar).toHaveAttribute(
        'aria-describedby',
        'account-avatar-help account-avatar-error'
      );
    }
    expect(patchBodies).toEqual([]);

    await events.clear(avatar);
    await events.type(avatar, '  https://images.example/avatar.png  ');
    avatar.focus();
    await events.keyboard('{Enter}');

    expect(await screen.findByText('Profile saved.')).toBeVisible();
    expect(patchBodies).toEqual([
      { name: 'Archive Person', avatar_url: 'https://images.example/avatar.png' },
    ]);
  }, 10_000);

  it('starts provider linking with a POST authorization URL and confirms unlink without exposing a final-identity failure as success', async () => {
    let unlinkAttempts = 0;
    const fetchMock = installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (path.endsWith('/account/identities/twitch/link'))
        return json({ authorization_url: 'https://twitch.example/authorize' });
      if (path.endsWith('/account/identities/google') && request.method === 'DELETE') {
        unlinkAttempts += 1;
        return json({ error: 'last_identity' }, 409);
      }
      return json({ error: 'unexpected' }, 500);
    });
    account = { ...account, identities: [googleIdentity], sessions: [currentSession] };
    const events = userEvent.setup();
    renderPage();
    await screen.findByText('Google');

    await events.click(screen.getByRole('button', { name: 'Link Twitch' }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([request]) => (request as Request).method === 'POST')).toBe(
        true
      )
    );
    const linkRequest = fetchMock.mock.calls
      .map(([request]) => request as Request)
      .find((request) => request.url.endsWith('/account/identities/twitch/link'));
    expect(linkRequest?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(window.location.href).toBe('https://twitch.example/authorize');

    // The UI prevents unlinking the sole identity before a destructive request is made.
    const unlink = screen.getByRole('button', { name: 'Unlink' });
    const explanation = screen.getByText('Keep at least one sign-in identity linked.');
    expect(explanation).toBeVisible();
    expect(explanation).toHaveAttribute('id', 'unlink-help-google');
    expect(unlink).toBeDisabled();
    expect(unlink).toHaveAttribute('aria-describedby', 'unlink-help-google');
    expect(unlinkAttempts).toBe(0);
  });

  it('redirects unauthenticated direct account access to sign in', async () => {
    installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user: null, capabilities: [] });
      return json({ error: 'unexpected' }, 500);
    });

    renderPage();

    expect(await screen.findByTestId('location')).toHaveTextContent('/login');
  });

  it('requires explicit confirmation and fresh OAuth proof before merging accounts', async () => {
    const fetchMock = installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) {
        return json({ user, role: 'moderator', capabilities: [] });
      }
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account')) {
        return json({ ...account, identities: [googleIdentity] });
      }
      if (path.endsWith('/account/identities/twitch/merge')) {
        return json({ authorization_url: 'https://twitch.example/merge-authorize' });
      }
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();

    renderPage('/account?error=identity_conflict&provider=twitch');

    expect(
      await screen.findByText(
        'That Twitch identity belongs to another HasanAra account. You can merge it into this account after confirming ownership again.'
      )
    ).toBeVisible();
    expect(screen.getByRole('alertdialog')).toHaveTextContent(
      'Other sessions and API keys from the absorbed account will be revoked.'
    );

    await events.click(screen.getByRole('button', { name: 'Merge and link Twitch' }));
    await waitFor(() =>
      expect(window.location.href).toBe('https://twitch.example/merge-authorize')
    );
    const mergeRequest = fetchMock.mock.calls
      .map(([request]) => request as Request)
      .find((request) => request.url.endsWith('/account/identities/twitch/merge'));
    expect(mergeRequest?.method).toBe('POST');
    expect(mergeRequest?.headers.get('X-CSRF-Token')).toBe('csrf-token');
  });

  it('cancels an account merge without starting another OAuth request', async () => {
    const fetchMock = installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account')) return json({ ...account, identities: [googleIdentity] });
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();

    renderPage('/account?error=identity_conflict&provider=twitch');
    await screen.findByRole('alertdialog');
    await events.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([request]) =>
        (request as Request).url.endsWith('/account/identities/twitch/merge')
      )
    ).toBe(false);
  });

  it('shows a retryable session error when auth initialization fails', async () => {
    installApi(() => Promise.reject(new Error('session service unavailable')));
    const events = userEvent.setup();
    renderPage();

    expect(
      await screen.findByRole(
        'heading',
        { name: 'Could not verify your session' },
        { timeout: 3000 }
      )
    ).toBeVisible();
    expect(screen.getByRole('alert')).toHaveTextContent('session service unavailable');
    const retry = screen.getByRole('button', { name: 'Try again' });
    retry.focus();
    expect(retry).toHaveFocus();
    await events.keyboard('{Enter}');
  });

  it('requires unlink confirmation and reports the backend last-identity guard without mutating the linked list', async () => {
    installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (path.endsWith('/account/identities/google')) return json({ error: 'last_identity' }, 409);
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    await screen.findByText('Google');

    await events.click(screen.getAllByRole('button', { name: 'Unlink' })[0]);
    expect(screen.getByText('Unlink Google?')).toBeVisible();
    await events.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText('Unlink Google?')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm unlink' })).not.toBeInTheDocument();

    await events.click(screen.getAllByRole('button', { name: 'Unlink' })[0]);
    await events.click(screen.getByRole('button', { name: 'Confirm unlink' }));
    expect(await screen.findByText('Your last sign-in identity must stay linked.')).toBeVisible();
    expect(screen.getByText('Google')).toBeVisible();
  });

  it('revokes an individual non-current session while keeping current auth', async () => {
    let meCalls = 0;
    const requests: Request[] = [];
    installApi((request) => {
      requests.push(request);
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) {
        meCalls += 1;
        return json(meCalls > 1 ? { user: null } : { user, role: 'moderator', capabilities: [] });
      }
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (path.endsWith('/account/sessions/session-other')) return json({ ok: true });
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    await screen.findByText('Other Browser');
    await events.click(screen.getByRole('button', { name: 'Revoke' }));
    await screen.findByText('Session revoked.');
    expect(
      requests
        .find((request) => request.url.endsWith('/account/sessions/session-other'))
        ?.headers.get('X-CSRF-Token')
    ).toBe('csrf-token');
  });

  it('logs out other sessions with keep_current=true while retaining the current session', async () => {
    const requests: Request[] = [];
    installApi((request) => {
      requests.push(request);
      const url = new URL(request.url);
      if (url.pathname.endsWith('/auth/me'))
        return json({ user, role: 'moderator', capabilities: [] });
      if (url.pathname.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (url.pathname.endsWith('/account') && request.method === 'GET') return json(account);
      if (url.pathname.endsWith('/account/sessions')) {
        account = { ...account, sessions: [currentSession] };
        return json({ revoked: 1 });
      }
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    await screen.findByText('Other Browser');
    await events.click(screen.getByRole('button', { name: 'Log out other sessions' }));
    expect(await screen.findByText('1 other session logged out.')).toBeVisible();
    const request = requests.find((item) => item.url.includes('/account/sessions?'));
    expect(new URL(request?.url ?? 'http://localhost').searchParams.get('keep_current')).toBe(
      'true'
    );
    expect(screen.getByText('Current Browser')).toBeVisible();
  });

  it('announces a failed session operation without removing the session', async () => {
    installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (path.endsWith('/account/sessions/session-other'))
        return json({ message: 'The session could not be revoked.' }, 422);
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();

    await screen.findByText('Other Browser');
    await events.click(screen.getByRole('button', { name: 'Revoke' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'That session could not be revoked.'
    );
    expect(screen.getByText('Other Browser')).toBeVisible();
  });

  it('shows an explicit empty state when no active sessions are returned', async () => {
    account = { ...account, sessions: [] };
    installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account')) return json(account);
      return json({ error: 'unexpected' }, 500);
    });

    renderPage();

    expect(await screen.findByText('No active sessions were returned.')).toBeVisible();
    expect(screen.getByRole('list', { name: 'Active sessions' })).toBeEmptyDOMElement();
  });

  it('clears authenticated state after revoking the current session', async () => {
    let signedIn = true;
    installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me'))
        return json({
          user: signedIn ? user : null,
          role: signedIn ? 'moderator' : null,
          capabilities: [],
        });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (
        path.endsWith('/account/sessions/session-current') ||
        path.endsWith('/account/sessions')
      ) {
        signedIn = false;
        return json({ ok: true, revoked: 2 });
      }
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    await screen.findByText('Current Browser');
    await events.click(screen.getByRole('button', { name: 'Sign out this session' }));
    expect(await screen.findByTestId('location')).toHaveTextContent('/');
  });

  it('clears authenticated state after logging out all sessions', async () => {
    let signedIn = true;
    const requests: Request[] = [];
    installApi((request) => {
      requests.push(request);
      const url = new URL(request.url);
      if (url.pathname.endsWith('/auth/me'))
        return json({ user: signedIn ? user : null, capabilities: [] });
      if (url.pathname.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (url.pathname.endsWith('/account') && request.method === 'GET') return json(account);
      if (url.pathname.endsWith('/account/sessions')) {
        signedIn = false;
        return json({ revoked: 2 });
      }
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    await screen.findByText('Current Browser');
    await events.click(screen.getByRole('button', { name: 'Log out all sessions' }));
    expect(await screen.findByTestId('location')).toHaveTextContent('/');
    const request = requests.find((item) => item.url.includes('/account/sessions?'));
    expect(new URL(request?.url ?? 'http://localhost').searchParams.get('keep_current')).toBe(
      'false'
    );
  });

  it('requires exact DELETE confirmation and only navigates after deletion succeeds', async () => {
    let deleteCalls = 0;
    installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me'))
        return json({ user: deleteCalls ? null : user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account') && request.method === 'GET') return json(account);
      if (path.endsWith('/account') && request.method === 'DELETE') {
        deleteCalls += 1;
        return deleteCalls === 1 ? json({ error: 'final_admin' }, 409) : json({ deleted: true });
      }
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();
    await screen.findByRole('button', { name: 'Delete account' });
    await events.click(screen.getByRole('button', { name: 'Delete account' }));
    const confirm = screen.getByRole('button', { name: 'Confirm deletion' });
    expect(confirm).toBeDisabled();
    await events.type(screen.getByLabelText(/Type DELETE/), 'delete');
    expect(confirm).toBeDisabled();
    await events.clear(screen.getByLabelText(/Type DELETE/));
    await events.type(screen.getByLabelText(/Type DELETE/), 'DELETE');
    await events.click(confirm);
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The final administrator account cannot be deleted.'
    );
    expect(screen.queryByTestId('location')).not.toBeInTheDocument();

    await events.click(screen.getByRole('button', { name: 'Confirm deletion' }));
    expect(await screen.findByTestId('location')).toHaveTextContent('/');
  });

  it('keeps deletion confirmation behind the danger-zone disclosure and clears it on cancel', async () => {
    installApi((request) => {
      const path = new URL(request.url).pathname;
      if (path.endsWith('/auth/me')) return json({ user, role: 'moderator', capabilities: [] });
      if (path.endsWith('/auth/csrf')) return json({ csrf_token: 'csrf-token' });
      if (path.endsWith('/account')) return json(account);
      return json({ error: 'unexpected' }, 500);
    });
    const events = userEvent.setup();
    renderPage();

    await screen.findByRole('heading', { name: 'Danger zone' });
    expect(screen.queryByLabelText(/Type DELETE/)).not.toBeInTheDocument();
    await events.click(screen.getByRole('button', { name: 'Delete account' }));
    const confirmation = screen.getByLabelText(/Type DELETE/);
    await events.type(confirmation, 'DELETE');
    await events.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByLabelText(/Type DELETE/)).not.toBeInTheDocument();
    await events.click(screen.getByRole('button', { name: 'Delete account' }));
    expect(screen.getByLabelText(/Type DELETE/)).toHaveValue('');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
