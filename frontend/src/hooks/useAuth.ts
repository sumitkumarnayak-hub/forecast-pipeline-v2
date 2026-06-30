"use client";

import { useEffect, useState } from "react";
import { canApprove as roleCanApprove, canWrite as roleCanWrite, getUser, type User } from "@/lib/auth";

/**
 * Client auth state safe for SSR hydration.
 * Until `hydrated` is true, `readOnly` is true and `canWrite` is false so server HTML matches the first client paint.
 */
export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setUser(getUser());
    setHydrated(true);
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
