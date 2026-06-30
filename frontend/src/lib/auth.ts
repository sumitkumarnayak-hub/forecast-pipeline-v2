/**
 * Auth helpers — user profile in sessionStorage; JWT in httpOnly cookie (set by API).
 */
import api from "./api";

export interface User {
  id: number;
  username: string;
  full_name: string;
  email: string;
  role: "admin" | "planner" | "viewer";
}

const USER_KEY = "ps_user";

export function saveUser(user: User) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(USER_KEY);
}

export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

/** Verify httpOnly session cookie via /me (also hydrates user cache). */
export async function fetchSession(): Promise<User | null> {
  try {
    const { data } = await api.get<User>("/api/auth/me");
    saveUser(data);
    return data;
  } catch {
    clearAuth();
    return null;
  }
}

export function isAuthenticated(): boolean {
  return !!getUser();
}

export async function logout(): Promise<void> {
  try {
    await api.post("/api/auth/logout");
  } catch {
    /* cookie may already be cleared */
  }
  clearAuth();
}

// RBAC helpers
export const canWrite = (role?: string) =>
  ["admin", "planner"].includes(role || "");
export const canApprove = (role?: string) => role === "admin";
export const isAdmin = (role?: string) => role === "admin";

export const ALLOWED_PAGES: Record<string, string[]> = {
  admin: [
    "Dashboard", "Auto-Pilot", "Baseline", "Master Data", "Product Launch",
    "Final Plan", "Validation", "Analytics", "Settings",
  ],
  planner: [
    "Dashboard", "Auto-Pilot", "Baseline", "Master Data", "Product Launch",
    "Final Plan", "Validation", "Analytics", "Settings",
  ],
  viewer: ["Dashboard", "Master Data", "Analytics", "Settings"],
};
