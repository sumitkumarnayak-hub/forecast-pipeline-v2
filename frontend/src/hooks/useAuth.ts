"use client";

import { useEffect, useState } from "react";
import {
  canApprove as roleCanApprove,
  canWrite as roleCanWrite,
  fetchSession,
  getUser,
  type User,
} from "@/lib/auth";

/**
 * Client auth state safe for SSR hydration.
 * Until `hydrated` is true, `readOnly` is true and `canWrite` is false.
 */
export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const cached = getUser();
    if (cached) setUser(cached);

    void fetchSession().then((sessionUser) => {
      if (cancelled) return;
      setUser(sessionUser);
      setHydrated(true);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const role = user?.role ?? "viewer";
  const activeRole = hydrated ? user?.role : undefined;

  return {
    user,
    role,
    hydrated,
    readOnly: !roleCanWrite(activeRole),
    canWrite: hydrated && roleCanWrite(user?.role),
    canApprove: hydrated && roleCanApprove(user?.role),
  };
}
