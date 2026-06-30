"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cacheGet, cacheSet } from "@/lib/queryCache";

type Options<T> = {
  cacheKey: string;
  fetcher: () => Promise<T>;
  ttlMs?: number;
  /** Refetch when these change (filters, etc.). */
  deps?: unknown[];
  enabled?: boolean;
};

/**
 * Stale-while-revalidate for arbitrary GET payloads (queryCache-backed).
 */
export function useStaleFetch<T>({
  cacheKey,
  fetcher,
  ttlMs = 300_000,
  deps = [],
  enabled = true,
}: Options<T>) {
  const [data, setData] = useState<T | null>(() => cacheGet<T>(cacheKey));
  const [loading, setLoading] = useState(() => !cacheGet<T>(cacheKey));
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const seq = useRef(0);

  const fetchFresh = useCallback(
    async (opts?: { showLoading?: boolean }) => {
      const showLoading = opts?.showLoading ?? false;
      if (showLoading) setLoading(true);
      else setRefreshing(true);
      const n = ++seq.current;
      try {
        const fresh = await fetcher();
        if (n !== seq.current) return;
        setData(fresh);
        cacheSet(cacheKey, fresh, ttlMs);
        setError("");
      } catch (e: unknown) {
        if (n !== seq.current) return;
        const err = e as { response?: { data?: { detail?: string } } };
        if (!cacheGet<T>(cacheKey)) {
          setError(err?.response?.data?.detail || "Failed to load");
        }
      } finally {
        if (n === seq.current) {
          if (showLoading) setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [cacheKey, fetcher, ttlMs],
  );

  useEffect(() => {
    if (!enabled) return;
    const cached = cacheGet<T>(cacheKey);
    if (cached) {
      setData(cached);
      setLoading(false);
      void fetchFresh();
    } else {
      void fetchFresh({ showLoading: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps drive refetch
  }, [cacheKey, enabled, ...deps]);

  const reload = useCallback(
    (force?: boolean) => {
      if (force) {
        try {
          sessionStorage.removeItem(`ps:${cacheKey}`);
        } catch {
          /* ignore */
        }
      }
      return fetchFresh({ showLoading: true });
    },
    [cacheKey, fetchFresh],
  );

  return { data, setData, loading, refreshing, error, reload };
}
