"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  canApprove as roleCanApprove,
  canWrite as roleCanWrite,
  establishSession as persistSession,
  getUser,
  resolveSession,
  type User,
} from "@/lib/auth";

type AuthContextValue = {
  user: User | null;
  role: string;
  hydrated: boolean;
  readOnly: boolean;
  canWrite: boolean;
  canApprove: boolean;
  establishSession: (user: User) => void;
  refreshSession: () => Promise<User | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [hydrated, setHydrated] = useState(false);

  const establishSession = useCallback((next: User) => {
    persistSession(next);
    setUser(next);
    setHydrated(true);
  }, []);

  const loadSession = useCallback(async (force = false) => {
    const next = await resolveSession({ force });
    if (next) {
      setUser(next);
    } else if (force || !getUser()) {
      setUser(null);
    }
    setHydrated(true);
    return next ?? getUser();
  }, []);

  useEffect(() => {
    const cached = getUser();
    if (cached) setUser(cached);
    void loadSession();
  }, [loadSession]);

  const role = user?.role ?? "viewer";
  const activeRole = hydrated ? user?.role : undefined;

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      role,
      hydrated,
      readOnly: !roleCanWrite(activeRole),
      canWrite: hydrated && roleCanWrite(user?.role),
      canApprove: hydrated && roleCanApprove(user?.role),
      establishSession,
      refreshSession: () => loadSession(true),
    }),
    [user, role, hydrated, activeRole, establishSession, loadSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
