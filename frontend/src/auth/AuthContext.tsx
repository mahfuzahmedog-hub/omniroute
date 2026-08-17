import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setAuthToken, type User } from "../api/client";

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const STORAGE_KEY = "forge.token";

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // On mount (or when the token changes) resolve the current user, clearing a stale token.
  useEffect(() => {
    let cancelled = false;
    async function resolve() {
      if (!token) {
        setUser(null);
        setLoading(false);
        return;
      }
      setAuthToken(token);
      try {
        const me = await api.me();
        if (!cancelled) setUser(me);
      } catch {
        if (!cancelled) {
          localStorage.removeItem(STORAGE_KEY);
          setToken(null);
          setAuthToken(null);
          setUser(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void resolve();
    return () => {
      cancelled = true;
    };
  }, [token]);

  function persist(newToken: string, newUser: User) {
    localStorage.setItem(STORAGE_KEY, newToken);
    setAuthToken(newToken);
    setToken(newToken);
    setUser(newUser);
    setLoading(false);
  }

  const value = useMemo<AuthState>(
    () => ({
      user,
      token,
      loading,
      login: async (email, password) => {
        const resp = await api.login(email, password);
        persist(resp.access_token, resp.user);
      },
      register: async (email, password, fullName) => {
        const resp = await api.register(email, password, fullName);
        persist(resp.access_token, resp.user);
      },
      logout: () => {
        localStorage.removeItem(STORAGE_KEY);
        setAuthToken(null);
        setToken(null);
        setUser(null);
      },
    }),
    [user, token, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
