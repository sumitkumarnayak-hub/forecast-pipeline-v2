/** In-memory + sessionStorage cache for instant UI (stale-while-revalidate). */

type CacheEntry<T> = { data: T; at: number; ttl: number };

const memory = new Map<string, CacheEntry<unknown>>();

function storageKey(key: string) {
  return `ps:${key}`;
}

export function cacheGet<T>(key: string): T | null {
  const hit = memory.get(key);
  if (hit && Date.now() - hit.at < hit.ttl) {
    return hit.data as T;
  }

  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(storageKey(key));
    if (!raw) return null;
    const entry = JSON.parse(raw) as CacheEntry<T>;
    if (Date.now() - entry.at >= entry.ttl) return null;
    memory.set(key, entry);
    return entry.data;
  } catch {
    return null;
  }
}

export function cacheSet<T>(key: string, data: T, ttlMs = 120_000): void {
  const entry: CacheEntry<T> = { data, at: Date.now(), ttl: ttlMs };
  memory.set(key, entry);
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(storageKey(key), JSON.stringify(entry));
  } catch {
    /* quota — memory cache still works */
  }
}

export function cacheInvalidate(key?: string): void {
  if (!key) {
    memory.clear();
    return;
  }
  memory.delete(key);
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(storageKey(key));
  } catch {
    /* ignore */
  }
}
