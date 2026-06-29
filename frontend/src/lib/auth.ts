/**
 * Auth helpers — token and user management in localStorage.
 */

export interface User {
  id: number;
  username: string;
  full_name: string;
  email: string;
  role: "admin" | "planner" | "viewer";
}

const TOKEN_KEY = "ps_token";
const USER_KEY = "ps_user";

export function saveAuth(token: string, user: User) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

// RBAC helpers
export const canWrite = (role?: string) =>
  ["admin", "planner"].includes(role || "");
export const canApprove = (role?: string) => role === "admin";
export const isAdmin = (role?: string) => role === "admin";

export const ALLOWED_PAGES: Record<string, string[]> = {
  admin: ["Dashboard", "Baseline", "Master Data", "Product Launch", "Final Plan", "Analytics", "Settings"],
  planner: ["Dashboard", "Baseline", "Master Data", "Product Launch", "Final Plan", "Analytics", "Settings"],
  viewer: ["Dashboard", "Master Data", "Analytics", "Settings"],
};
