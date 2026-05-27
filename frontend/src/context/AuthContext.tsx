import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { getAuthConfig, getAuthSession, logout as logoutRequest } from '../services/api';
import type { AuthConfig, AuthUser } from '../types';

type AuthContextValue = {
  initialized: boolean;
  loading: boolean;
  authenticated: boolean;
  authEnabled: boolean;
  config: AuthConfig | null;
  user: AuthUser | null;
  refreshSession: () => Promise<void>;
  login: (nextPath?: string) => void;
  signup: (nextPath?: string) => void;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function buildRedirectUrl(path: string, nextPath?: string) {
  const url = new URL(path, window.location.origin);
  if (nextPath) {
    url.searchParams.set('next', nextPath);
  }
  return url.toString();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [initialized, setInitialized] = useState(false);
  const [loading, setLoading] = useState(true);

  const refreshSession = async () => {
    setLoading(true);
    try {
      const nextConfig = await getAuthConfig();
      setConfig(nextConfig);

      const session = await getAuthSession();
      setUser(session.user ?? null);
    } catch (error) {
      console.error('Failed to load auth session:', error);
      setConfig(null);
      setUser(null);
    } finally {
      setLoading(false);
      setInitialized(true);
    }
  };

  useEffect(() => {
    refreshSession();
  }, []);

  const login = (nextPath = '/') => {
    const target = config?.login_url || '/api/auth/entra/login';
    window.location.assign(buildRedirectUrl(target, nextPath));
  };

  const signup = (nextPath = '/') => {
    const target = config?.signup_url || '/api/auth/entra/login?prompt=create';
    window.location.assign(buildRedirectUrl(target, nextPath));
  };

  const logout = async () => {
    await logoutRequest();
    setUser(null);
    window.location.assign('/login');
  };

  const value: AuthContextValue = {
    initialized,
    loading,
    authenticated: Boolean(user),
    authEnabled: Boolean(config?.enabled),
    config,
    user,
    refreshSession,
    login,
    signup,
    logout
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuthContext() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuthContext must be used inside AuthProvider');
  }
  return value;
}
