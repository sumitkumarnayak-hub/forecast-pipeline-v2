/** Shared sessionStorage bootstrap cache (stale-while-revalidate). */

export function readSessionBootstrap<T>(key: string, ttlMs: number): T | null {
  const hit = readSessionBootstrapEntry<T>(key, ttlMs);
  return hit?.data ?? null;
}

export function readSessionBootstrapEntry<T>(
  key: string,
  ttlMs: number,
): { data: T; ageMs: number } | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const { ts, data } = JSON.parse(raw) as { ts: number; data: T };
    const ageMs = Date.now() - ts;
    if (ageMs > ttlMs) return null;
    return { data, ageMs };
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

/** Internal tool — keep bootstraps warm for 5 minutes. */
export const BOOTSTRAP_TTL_MS = 300_000;
