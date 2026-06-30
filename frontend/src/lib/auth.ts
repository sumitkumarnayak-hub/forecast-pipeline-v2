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
const VERIFIED_AT_KEY = "ps_user_verified_at";
const SESSION_VERIFY_TTL_MS = 90_000;

let sessionInflight: Promise<User | null> | null = null;
let sessionGeneration = 0;

export function saveUser(user: User) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  sessionStorage.setItem(VERIFIED_AT_KEY, String(Date.now()));
}

/** Call immediately after a successful login (before /me round-trip). */
export function establishSession(user: User) {
  saveUser(user);
  sessionGeneration += 1;
}

export function clearAuth() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(USER_KEY);
  sessionStorage.removeItem(VERIFIED_AT_KEY);
  sessionGeneration += 1;
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

function recentlyVerified(): boolean {
  if (typeof window === "undefined") return false;
  const raw = sessionStorage.getItem(VERIFIED_AT_KEY);
  if (!raw) return false;
  const ts = Number(raw);
  return Number.isFinite(ts) && Date.now() - ts < SESSION_VERIFY_TTL_MS;
}

export async function resolveSession(options?: { force?: boolean }): Promise<User | null> {
  const force = options?.force ?? false;
  const cached = getUser();
  if (!force && cached && recentlyVerified()) {
    return cached;
  }
  if (sessionInflight && !force) {
    return sessionInflight;
  }

  const gen = sessionGeneration;

  sessionInflight = api
    .get<User>("/api/auth/me")
    .then(({ data }) => {
      if (gen !== sessionGeneration) {
        return getUser();
      }
      saveUser(data);
      return data;
    })
    .catch(() => {
      if (gen !== sessionGeneration || recentlyVerified()) {
        return getUser();
      }
      clearAuth();
      return null;
    })
    .finally(() => {
      sessionInflight = null;
    });

  return sessionInflight;
}

export const fetchSession = resolveSession;

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
