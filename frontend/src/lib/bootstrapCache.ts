/** Shared sessionStorage bootstrap cache (stale-while-revalidate). */

export function readSessionBootstrap<T>(key: string, ttlMs: number): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const { ts, data } = JSON.parse(raw) as { ts: number; data: T };
    if (Date.now() - ts > ttlMs) return null;
    return data;
  } catch {
    return null;
  }
}

export function writeSessionBootstrap<T>(key: string, data: T): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }));
  } catch {
    /* quota */
  }
}

export const BOOTSTRAP_TTL_MS = 120_000;
