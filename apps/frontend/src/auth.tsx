// Global auth state: who is logged in, and helpers to log in/out.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { ApiError, auth as authApi } from './api';
import { isTelegramMiniApp } from './telegram';
import type { Me, TelegramAuthPayload } from './types';

interface AuthState {
  user: Me | null;
  loading: boolean;
  isMiniApp: boolean;
  refresh: () => Promise<void>;
  loginWithTelegram: (payload: TelegramAuthPayload) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const isMiniApp = useMemo(() => isTelegramMiniApp(), []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const me = await authApi.me();
      setUser(me);
    } catch (err) {
      // 401 simply means "not logged in" — not an error worth surfacing.
      if (!(err instanceof ApiError) || err.status !== 401) {
        // eslint-disable-next-line no-console
        console.warn('auth refresh failed', err);
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loginWithTelegram = useCallback(
    async (payload: TelegramAuthPayload) => {
      await authApi.telegramLogin(payload);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthState>(
    () => ({ user, loading, isMiniApp, refresh, loginWithTelegram, logout }),
    [user, loading, isMiniApp, refresh, loginWithTelegram, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
