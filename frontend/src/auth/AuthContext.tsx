import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { getAuth } from '@/api/endpoints/auth/auth';
import { clearToken, setToken } from '@/api/custom-instance';
import type { Permission } from '@/api/model';
import { type AuthUser } from './types';

type AuthContextValue = {
  user: AuthUser | null;
  /** Mientras se revalida la sesion guardada no sabemos todavia si hay usuario. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: Permission) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const USER_KEY = 'hosp_auth_user';

function storedUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const api = getAuth();
  const [user, setUser] = useState<AuthUser | null>(storedUser);
  const [loading, setLoading] = useState(Boolean(storedUser()));

  // La sesion vive en el servidor: al abrir la app se revalida el token guardado, asi una
  // sesion vencida o cerrada desde otro lado no deja la pantalla adentro.
  useEffect(() => {
    if (!user) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    api
      .meApiV1AuthMeGet()
      .then((current) => {
        if (cancelled) return;
        const refreshed = { ...current.user, permissions: current.permissions };
        localStorage.setItem(USER_KEY, JSON.stringify(refreshed));
        setUser(refreshed);
      })
      .catch(() => {
        if (cancelled) return;
        clearToken();
        localStorage.removeItem(USER_KEY);
        setUser(null);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // Solo al montar: revalidar en cada cambio de usuario haria un pedido tras el login.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await api.loginApiV1AuthLoginPost({ email, password });
      setToken(session.token);
      const next = { ...session.user, permissions: session.permissions };
      localStorage.setItem(USER_KEY, JSON.stringify(next));
      setUser(next);
    },
    [api],
  );

  const logout = useCallback(async () => {
    try {
      await api.logoutApiV1AuthLogoutPost();
    } catch {
      // La sesion ya no valia: igual se sale.
    }
    clearToken();
    localStorage.removeItem(USER_KEY);
    setUser(null);
  }, [api]);

  const can = useCallback(
    (permission: Permission) => Boolean(user?.permissions.includes(permission)),
    [user],
  );

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
