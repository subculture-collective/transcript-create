import { createContext, useContext, useEffect, useState } from 'react';
import { buildApiUrl, http } from './api';

type User = {
  id: string;
  email?: string | null;
  name?: string | null;
  avatar_url?: string | null;
  plan?: string | null;
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
          window.location.href = buildApiUrl('auth/login/google');
        },
        loginTwitch: () => {
          window.location.href = buildApiUrl('auth/login/twitch');
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

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error('AuthProvider missing');
  return ctx;
}
