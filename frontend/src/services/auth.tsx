import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { buildApiUrl, http, setCsrfToken } from './api';
import type { OAuthProvider, UserRole } from '../types/api';

export type User = {
  id: string;
  email?: string | null;
  name?: string | null;
  avatar_url?: string | null;
  plan?: string | null;
  role?: UserRole | null;
};

type AuthEnvelope = {
  user: User | null;
  role?: UserRole | null;
  capabilities?: string[];
};

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'error';

export type AuthState = {
  user: User | null;
  loading: boolean;
  status: AuthStatus;
  error: string | null;
  role: UserRole | null;
  capabilities: string[];
  refresh: () => Promise<void>;
  invalidateLocalAuth: (options?: { preserveUser?: boolean }) => void;
  login: () => void;
  loginTwitch: () => void;
  loginWith: (provider: OAuthProvider) => void;
  linkProvider: (provider: OAuthProvider) => Promise<void>;
  mergeProvider: (provider: OAuthProvider) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Authentication request failed';
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const userRef = useRef<User | null>(null);
  const authGeneration = useRef(0);
  const refreshController = useRef<AbortController | null>(null);

  useEffect(() => {
    userRef.current = user;
  }, [user]);

  const invalidateLocalAuth = useCallback((options?: { preserveUser?: boolean }) => {
    authGeneration.current += 1;
    refreshController.current?.abort();
    refreshController.current = null;
    if (!options?.preserveUser) setCsrfToken(null);
    setRole(null);
    setCapabilities([]);
    setError(null);
    if (options?.preserveUser) {
      setStatus(userRef.current ? 'authenticated' : 'anonymous');
      return;
    }
    setUser(null);
    setStatus('anonymous');
  }, []);

  const refresh = useCallback(async () => {
    refreshController.current?.abort();
    const controller = new AbortController();
    refreshController.current = controller;
    const generation = ++authGeneration.current;
    const isCurrent = () => generation === authGeneration.current && !controller.signal.aborted;

    if (!userRef.current) setStatus('loading');
    try {
      const response = await http
        .get('auth/me', { signal: controller.signal })
        .json<AuthEnvelope>();
      if (!isCurrent()) return;

      if (response.user) {
        // Keep an existing token usable while the replacement is fetched.
        // Clearing it at refresh start creates a needless mutation failure window.
        const csrf = await http
          .get('auth/csrf', { signal: controller.signal })
          .json<{ csrf_token: string }>();
        if (!isCurrent()) return;
        setCsrfToken(csrf.csrf_token);
      } else {
        if (!isCurrent()) return;
        setCsrfToken(null);
      }
      if (!isCurrent()) return;
      setUser(response.user);
      setRole(response.role ?? null);
      setCapabilities(response.capabilities ?? []);
      setError(null);
      setStatus(response.user ? 'authenticated' : 'anonymous');
    } catch (requestError: unknown) {
      if (!isCurrent()) return;
      setCsrfToken(null);
      setUser(null);
      setRole(null);
      setCapabilities([]);
      setError(errorMessage(requestError));
      setStatus('error');
      throw requestError;
    }
  }, []);

  useEffect(() => {
    void refresh().catch(() => {
      // The provider has already recorded the error; avoid an unhandled rejection.
    });
    return () => {
      authGeneration.current += 1;
      refreshController.current?.abort();
    };
  }, [refresh]);
  return (
    <AuthCtx.Provider
      value={{
        user,
        loading: status === 'loading',
        status,
        error,
        role,
        capabilities,
        refresh,
        invalidateLocalAuth,
        login: () => {
          window.location.href = buildApiUrl('auth/login/google');
        },
        loginTwitch: () => {
          window.location.href = buildApiUrl('auth/login/twitch');
        },
        loginWith: (provider: OAuthProvider) => {
          window.location.href = buildApiUrl(`auth/login/${provider}`);
        },
        linkProvider: async (provider: OAuthProvider) => {
          const response = await http
            .post(`account/identities/${provider}/link`)
            .json<{ authorization_url: string }>();
          window.location.href = response.authorization_url;
        },
        mergeProvider: async (provider: OAuthProvider) => {
          const response = await http
            .post(`account/identities/${provider}/merge`)
            .json<{ authorization_url: string }>();
          window.location.href = response.authorization_url;
        },
        logout: async () => {
          // Stop older refresh responses from restoring auth while logout is in flight.
          const generation = ++authGeneration.current;
          refreshController.current?.abort();
          refreshController.current = null;
          const isCurrent = () => generation === authGeneration.current;

          try {
            await http.post('auth/logout').json();
            if (!isCurrent()) return;
            invalidateLocalAuth();
          } catch (requestError: unknown) {
            if (!isCurrent()) return;
            // A failed logout does not prove that the server session is gone.
            // Retain local auth and the CSRF token so the user can retry.
            setError(errorMessage(requestError));
            setStatus('error');
          }
        },
      }}
    >
      {children}
    </AuthCtx.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error('AuthProvider missing');
  return ctx;
}
