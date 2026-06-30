import api from "@/lib/api";
import { cacheGet, cacheSet } from "@/lib/queryCache";
import { fetchOnce } from "@/lib/fetchOnce";

export const BASELINE_APPROVED_KEY = "shell:baseline-approved";
const BASELINE_STATUS_TTL = 600_000;

export async function fetchBaselineStatus(options?: { force?: boolean }): Promise<boolean> {
  if (!options?.force) {
    const cached = cacheGet<boolean>(BASELINE_APPROVED_KEY);
    if (cached !== null) return cached;
  }

  return fetchOnce("api:baseline:status", async () => {
    const { data } = await api.get<{ approved?: boolean }>("/api/baseline/status");
    const approved = Boolean(data.approved);
    cacheSet(BASELINE_APPROVED_KEY, approved, BASELINE_STATUS_TTL);
    return approved;
  });
}
