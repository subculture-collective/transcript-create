import { createContext, useContext, useEffect, useState } from 'react';
import { http } from './api';

type User = {
  id: string;
  email?: string | null;
  name?: string | null;
  avatar_url?: string | null;
  plan?: string | null;
  searches_used_today?: number | null;
  search_limit?: number | null;
};

type AuthState = {
  user: User | null;
  loading: boolean;
  login: () => void;
  loginTwitch: () => void;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    http
      .get('auth/me')
      .json<{ user: User | null }>()
      .then((r) => setUser(r.user))
      .finally(() => setLoading(false));
  }, []);
  return (
    <AuthCtx.Provider
      value={{
        user,
        loading,
        login: () => {
          window.location.href = '/api/auth/login/google';
        },
        loginTwitch: () => {
          window.location.href = '/api/auth/login/twitch';
        },
        logout: async () => {
          await http
            .post('auth/logout')
            .json()
            .catch(() => {});
          setUser(null);
        },
      }}
    >
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error('AuthProvider missing');
  return ctx;
}
