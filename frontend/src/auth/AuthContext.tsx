import { createContext, useContext, useState, type ReactNode } from 'react';
import { type AuthUser, type Role } from './types';

type AuthContextValue = {
  user: AuthUser | null;
  login: (role: Role, name: string, email: string) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const STORAGE_KEY = 'hosp_auth_user';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        return JSON.parse(raw) as AuthUser;
      } catch {
        return null;
      }
    }
    return null;
  });

  const login = (role: Role, name: string, email: string) => {
    const u: AuthUser = { role, name, email };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(u));
    localStorage.setItem('hosp_auth_token', 'mock-jwt-' + role);
    setUser(u);
  };

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem('hosp_auth_token');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
