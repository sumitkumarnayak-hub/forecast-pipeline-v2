/** Dedupe concurrent identical API reads (e.g. /me, baseline status). */

const inflight = new Map<string, Promise<unknown>>();

export async function fetchOnce<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;
  const job = fn().finally(() => {
    inflight.delete(key);
  });
  inflight.set(key, job);
  return job;
}
