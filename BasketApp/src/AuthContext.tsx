import React, { createContext, useContext, useState, useEffect } from 'react';
import { api, loadStoredToken, clearToken } from './api/client';

interface User {
  id: number;
  username: string;
  display_name: string;
  email: string;
  is_admin: boolean;
  currency: string;
  permissions: string[];
}
interface AuthCtx {
  user: User | null;
  setUser: (u: User | null) => void;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>({ user: null, setUser: () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      await loadStoredToken();
      try {
        const me = await api.me();
        setUser(me);
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const logout = async () => {
    await api.logout();
    clearToken();
    setUser(null);
  };

  if (loading) return null;
  return <Ctx.Provider value={{ user, setUser, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
