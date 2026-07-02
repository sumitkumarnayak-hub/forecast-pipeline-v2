/** Client cache for manual Auto-Pilot sync (instant re-open). */
import api from "@/lib/api";

export type ManualSyncStep = {
  index: number;
  key: string;
  name: string;
  detected: boolean;
  confidence: string;
  message: string;
  evidence: string;
};

export type ManualSyncResult = {
  completed_steps: number[];
  suggested_from_step: number;
  steps: ManualSyncStep[];
  summary: string;
  checked_at: string;
};

const CACHE_KEY = "autopilot:manual-sync";
const TTL_MS = 25_000;

type CacheEntry = { at: number; data: ManualSyncResult };

function readCache(): ManualSyncResult | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const entry = JSON.parse(raw) as CacheEntry;
    if (Date.now() - entry.at > TTL_MS) {
      sessionStorage.removeItem(CACHE_KEY);
      return null;
    }
    return entry.data;
  } catch {
    return null;
  }
}

function writeCache(data: ManualSyncResult) {
  if (typeof sessionStorage === "undefined") return;
  try {
    const entry: CacheEntry = { at: Date.now(), data };
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(entry));
  } catch {
    /* quota */
  }
}

export function clearManualSyncCache() {
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.removeItem(CACHE_KEY);
  }
}

export async function fetchManualSync(options?: {
  refresh?: boolean;
  preferCache?: boolean;
}): Promise<ManualSyncResult> {
  const preferCache = options?.preferCache !== false;
  if (preferCache && !options?.refresh) {
    const hit = readCache();
    if (hit) return hit;
  }

  const { data } = await api.get<ManualSyncResult>("/api/autopilot/manual-sync", {
    params: options?.refresh ? { refresh: true } : undefined,
  });
  writeCache(data);
  return data;
}

/** Background warm — does not throw to caller. */
export function prefetchManualSync(): void {
  const hit = readCache();
  if (hit) return;
  void fetchManualSync({ preferCache: false }).catch(() => {});
}
