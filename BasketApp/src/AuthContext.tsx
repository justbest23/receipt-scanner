import React, { createContext, useContext, useState, useEffect } from 'react';
import { api } from './api/client';

interface User { id: number; username: string; display_name: string; email: string; is_admin: boolean; }
interface AuthCtx { user: User | null; setUser: (u: User | null) => void; logout: () => Promise<void>; }

const Ctx = createContext<AuthCtx>({ user: null, setUser: () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
  }, []);

  const logout = async () => {
    await api.logout().catch(() => {});
    setUser(null);
  };

  if (loading) return null;
  return <Ctx.Provider value={{ user, setUser, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
