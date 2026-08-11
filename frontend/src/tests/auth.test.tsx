import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { Input } from 'ky';
import { AuthProvider, useAuth } from '../services/auth';
import { buildApiUrl, http, setCsrfToken } from '../services/api';

// Test component that uses auth
function TestComponent() {
  const {
    user,
    loading,
    status,
    error,
    role,
    capabilities,
    refresh,
    invalidateLocalAuth,
    login,
    loginTwitch,
    logout,
  } = useAuth();

  if (loading)
    return (
      <div>
        <div>Loading...</div>
        <button onClick={() => invalidateLocalAuth()}>Invalidate</button>
      </div>
    );

  return (
    <div>
      <div data-testid="user">{user ? user.email : 'No user'}</div>
      <div data-testid="status">{status}</div>
      <div data-testid="error">{error ?? 'No error'}</div>
      <div data-testid="role">{role ?? 'No role'}</div>
      <div data-testid="capabilities">{capabilities.join(',')}</div>
      <button onClick={login}>Login Google</button>
      <button onClick={loginTwitch}>Login Twitch</button>
      <button onClick={() => void refresh()}>Refresh</button>
      <button onClick={() => invalidateLocalAuth()}>Invalidate</button>
      <button onClick={logout}>Logout</button>
    </div>
  );
}

describe('auth service', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    setCsrfToken(null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).location;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    window.location = { href: '' } as any;
  });

  describe('AuthProvider', () => {
    it('shows loading state initially', () => {
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockImplementation(
          () => new Promise(() => {}) // Never resolves
        ),
      });
      vi.spyOn(http, 'get').mockImplementation(getMock);

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('loads user data on mount', async () => {
      const mockUser = { id: '1', email: 'test@example.com', name: 'Test User' };
      const fetchMock = vi.fn((input: RequestInfo | URL) => {
        const url = input instanceof Request ? input.url : String(input);
        if (url.endsWith('auth/me')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ user: mockUser, role: 'admin', capabilities: ['admin:access'] })
            )
          );
        }
        if (url.endsWith('auth/csrf')) {
          return Promise.resolve(
            new Response(JSON.stringify({ csrf_token: 'acquired-csrf-token' }))
          );
        }
        return Promise.reject(new Error(`Unexpected request: ${url}`));
      });
      vi.stubGlobal('fetch', fetchMock);

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
      });

      expect(fetchMock.mock.calls.map(([request]) => (request as Request).url)).toEqual(
        expect.arrayContaining([
          expect.stringMatching(/auth\/me$/),
          expect.stringMatching(/auth\/csrf$/),
        ])
      );
      expect(screen.getByTestId('role')).toHaveTextContent('admin');
      expect(screen.getByTestId('capabilities')).toHaveTextContent('admin:access');
    });

    it('handles no user logged in', async () => {
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue({ user: null }),
      });
      vi.spyOn(http, 'get').mockImplementation(getMock);

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('No user');
      });
    });

    it('reports API errors without an unhandled rejection', async () => {
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockRejectedValue(new Error('Network error')),
      });
      vi.spyOn(http, 'get').mockImplementation(getMock);

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      // Should still render after error
      await waitFor(() => {
        expect(screen.getByTestId('status')).toHaveTextContent('error');
        expect(screen.getByTestId('error')).toHaveTextContent('Network error');
        expect(screen.getByTestId('user')).toHaveTextContent('No user');
      });
    });

    it('keeps only the newest refresh response and CSRF token', async () => {
      let resolveOlder: ((response: Response) => void) | undefined;
      let meCalls = 0;
      const fetchMock = vi.fn((request: Request) => {
        const path = new URL(request.url).pathname;
        if (path.endsWith('/auth/me')) {
          meCalls += 1;
          if (meCalls === 1)
            return Promise.resolve(
              new Response(
                JSON.stringify({ user: { id: 'initial', email: 'initial@example.com' } })
              )
            );
          if (meCalls === 2) return new Promise<Response>((resolve) => (resolveOlder = resolve));
          return Promise.resolve(
            new Response(
              JSON.stringify({
                user: { id: 'new', email: 'new@example.com' },
                role: 'moderator',
                capabilities: ['archive:read'],
              })
            )
          );
        }
        if (path.endsWith('/auth/csrf'))
          return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'new-csrf' })));
        if (path.endsWith('/account')) return Promise.resolve(new Response('{}'));
        return Promise.reject(new Error(`Unexpected request: ${path}`));
      });
      vi.stubGlobal('fetch', fetchMock);
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await screen.findByText('initial@example.com');
      await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'));
      fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
      await waitFor(() => expect(resolveOlder).toBeDefined());
      fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
      await screen.findByText('new@example.com');
      resolveOlder?.(
        new Response(
          JSON.stringify({
            user: { id: 'old', email: 'old@example.com' },
            role: 'admin',
            capabilities: ['admin:access'],
          })
        )
      );
      await waitFor(() => expect(screen.queryByText('old@example.com')).not.toBeInTheDocument());
      expect(screen.getByTestId('role')).toHaveTextContent('moderator');
      expect(screen.getByTestId('capabilities')).toHaveTextContent('archive:read');

      await http.post('account').json();
      const request = fetchMock.mock.calls.at(-1)?.[0] as Request;
      expect(request.headers.get('X-CSRF-Token')).toBe('new-csrf');
    });

    it('cannot restore auth or CSRF from a refresh delayed past explicit invalidation', async () => {
      let resolveRefresh: ((response: Response) => void) | undefined;
      let meCalls = 0;
      const fetchMock = vi.fn((request: Request) => {
        const path = new URL(request.url).pathname;
        if (path.endsWith('/auth/me')) {
          meCalls += 1;
          if (meCalls === 1)
            return Promise.resolve(
              new Response(JSON.stringify({ user: { id: '1', email: 'me@example.com' } }))
            );
          return new Promise<Response>((resolve) => (resolveRefresh = resolve));
        }
        if (path.endsWith('/auth/csrf'))
          return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'csrf' })));
        if (path.endsWith('/account')) return Promise.resolve(new Response('{}'));
        return Promise.reject(new Error(`Unexpected request: ${path}`));
      });
      vi.stubGlobal('fetch', fetchMock);
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );
      await screen.findByText('me@example.com');
      fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
      await waitFor(() => expect(resolveRefresh).toBeDefined());
      fireEvent.click(screen.getByRole('button', { name: 'Invalidate' }));
      resolveRefresh?.(
        new Response(JSON.stringify({ user: { id: 'stale', email: 'stale@example.com' } }))
      );
      await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('No user'));

      await http.post('account').json();
      const request = fetchMock.mock.calls.at(-1)?.[0] as Request;
      expect(request.headers.get('X-CSRF-Token')).toBeNull();
    });

    it('keeps the prior CSRF token usable while an authenticated refresh replaces it', async () => {
      let csrfCalls = 0;
      let resolveReplacement: ((response: Response) => void) | undefined;
      const fetchMock = vi.fn((request: Request) => {
        const path = new URL(request.url).pathname;
        if (path.endsWith('/auth/me'))
          return Promise.resolve(
            new Response(JSON.stringify({ user: { id: '1', email: 'me@example.com' } }))
          );
        if (path.endsWith('/auth/csrf')) {
          csrfCalls += 1;
          if (csrfCalls === 1)
            return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'old-csrf' })));
          return new Promise<Response>((resolve) => (resolveReplacement = resolve));
        }
        if (path.endsWith('/account')) return Promise.resolve(new Response('{}'));
        return Promise.reject(new Error(`Unexpected request: ${path}`));
      });
      vi.stubGlobal('fetch', fetchMock);
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );
      await screen.findByText('me@example.com');
      fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
      await waitFor(() => expect(resolveReplacement).toBeDefined());

      await http.post('account').json();
      const unsafeRequest = fetchMock.mock.calls.at(-1)?.[0] as Request;
      expect(unsafeRequest.headers.get('X-CSRF-Token')).toBe('old-csrf');
      resolveReplacement?.(new Response(JSON.stringify({ csrf_token: 'replacement-csrf' })));
    });
  });

  it('injects the memory-only CSRF token on unsafe requests', async () => {
    setCsrfToken('csrf-memory-token');
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await http.post('auth/logout').json();
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.get('X-CSRF-Token')).toBe('csrf-memory-token');
    expect(localStorage.getItem('csrf_token')).not.toBe('csrf-memory-token');
  });

  describe('useAuth', () => {
    it('throws error when used outside AuthProvider', () => {
      // Suppress console.error for this test
      const originalError = console.error;
      console.error = vi.fn();

      expect(() => {
        render(<TestComponent />);
      }).toThrow('AuthProvider missing');

      console.error = originalError;
    });
  });

  describe('login methods', () => {
    it('redirects to Google login', async () => {
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue({ user: null }),
      });
      vi.spyOn(http, 'get').mockImplementation(getMock);

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByText('Login Google')).toBeInTheDocument();
      });

      const loginBtn = screen.getByText('Login Google');
      loginBtn.click();

      expect(window.location.href).toBe(buildApiUrl('auth/login/google'));
    });

    it('redirects to Twitch login', async () => {
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue({ user: null }),
      });
      vi.spyOn(http, 'get').mockImplementation(getMock);

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByText('Login Twitch')).toBeInTheDocument();
      });

      const loginBtn = screen.getByText('Login Twitch');
      loginBtn.click();

      expect(window.location.href).toBe(buildApiUrl('auth/login/twitch'));
    });

    it('acquires a CSRF token and sends it through Ky on logout', async () => {
      const mockUser = { id: '1', email: 'test@example.com' };
      const fetchMock = vi.fn((input: RequestInfo | URL) => {
        const request = input as Request;
        if (request.url.endsWith('auth/me'))
          return Promise.resolve(new Response(JSON.stringify({ user: mockUser })));
        if (request.url.endsWith('auth/csrf'))
          return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'logout-csrf-token' })));
        if (request.url.endsWith('auth/logout')) return Promise.resolve(new Response('{}'));
        return Promise.reject(new Error(`Unexpected request: ${request.url}`));
      });
      vi.stubGlobal('fetch', fetchMock);

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
      });

      const logoutBtn = screen.getByText('Logout');
      logoutBtn.click();

      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('No user');
      });
      const logoutRequest = fetchMock.mock.calls
        .map(([request]) => request as Request)
        .find((request) => request.url.endsWith('auth/logout'));
      expect(logoutRequest?.headers.get('X-CSRF-Token')).toBe('logout-csrf-token');
    });

    it('handles logout errors gracefully', async () => {
      const mockUser = { id: '1', email: 'test@example.com' };
      const getMock = vi.fn().mockReturnValue({
        json: vi.fn().mockResolvedValue({ user: mockUser }),
      });
      const postMock = vi.fn().mockReturnValue({
        json: vi.fn().mockRejectedValue(new Error('Network error')),
      });
      vi.spyOn(http, 'get').mockImplementation(getMock);
      vi.spyOn(http, 'post').mockImplementation(postMock);

      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
      });

      const logoutBtn = screen.getByText('Logout');
      logoutBtn.click();

      // A failed server logout must not create a false local signed-out state.
      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
        expect(screen.getByTestId('status')).toHaveTextContent('error');
        expect(screen.getByTestId('error')).toHaveTextContent('Network error');
      });
    });

    it('does not let an older logout failure overwrite a newer successful refresh', async () => {
      let rejectLogout: ((error: Error) => void) | undefined;
      const mockUser = { id: '1', email: 'test@example.com' };
      const fetchMock = vi.fn((input: Input) => {
        const url = input instanceof Request ? input.url : String(input);
        const path = new URL(url, 'http://localhost').pathname;
        return Promise.resolve(
          new Response(
            JSON.stringify(
              path.endsWith('/auth/csrf')
                ? { csrf_token: 'refresh-csrf-token' }
                : { user: mockUser }
            )
          )
        );
      });
      const postMock = vi.fn().mockReturnValue({
        json: vi
          .fn()
          .mockImplementation(() => new Promise<never>((_, reject) => (rejectLogout = reject))),
      });
      vi.stubGlobal('fetch', fetchMock);
      vi.spyOn(http, 'post').mockImplementation(postMock);
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await screen.findByText('test@example.com');
      fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
      await waitFor(() => expect(rejectLogout).toBeDefined());
      fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
      await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'));
      rejectLogout?.(new Error('Stale logout failure'));

      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
        expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
        expect(screen.getByTestId('error')).toHaveTextContent('No error');
      });
    });

    it('does not let an older logout failure overwrite explicit local invalidation', async () => {
      let rejectLogout: ((error: Error) => void) | undefined;
      const mockUser = { id: '1', email: 'test@example.com' };
      const getMock = vi
        .fn()
        .mockReturnValue({ json: vi.fn().mockResolvedValue({ user: mockUser }) });
      const postMock = vi.fn().mockReturnValue({
        json: vi
          .fn()
          .mockImplementation(() => new Promise<never>((_, reject) => (rejectLogout = reject))),
      });
      vi.spyOn(http, 'get').mockImplementation(getMock);
      vi.spyOn(http, 'post').mockImplementation(postMock);
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await screen.findByText('test@example.com');
      fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
      await waitFor(() => expect(rejectLogout).toBeDefined());
      fireEvent.click(screen.getByRole('button', { name: 'Invalidate' }));
      rejectLogout?.(new Error('Stale logout failure'));

      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('No user');
        expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
        expect(screen.getByTestId('error')).toHaveTextContent('No error');
      });
    });

    it('reports a delayed failure from the latest logout request', async () => {
      let rejectLogout: ((error: Error) => void) | undefined;
      const mockUser = { id: '1', email: 'test@example.com' };
      const getMock = vi
        .fn()
        .mockReturnValue({ json: vi.fn().mockResolvedValue({ user: mockUser }) });
      const postMock = vi.fn().mockReturnValue({
        json: vi
          .fn()
          .mockImplementation(() => new Promise<never>((_, reject) => (rejectLogout = reject))),
      });
      vi.spyOn(http, 'get').mockImplementation(getMock);
      vi.spyOn(http, 'post').mockImplementation(postMock);
      render(
        <AuthProvider>
          <TestComponent />
        </AuthProvider>
      );

      await screen.findByText('test@example.com');
      fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
      await waitFor(() => expect(rejectLogout).toBeDefined());
      rejectLogout?.(new Error('Delayed network error'));

      await waitFor(() => {
        expect(screen.getByTestId('user')).toHaveTextContent('test@example.com');
        expect(screen.getByTestId('status')).toHaveTextContent('error');
        expect(screen.getByTestId('error')).toHaveTextContent('Delayed network error');
      });
    });
  });
});
