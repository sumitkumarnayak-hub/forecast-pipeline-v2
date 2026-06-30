"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cacheGet, cacheInvalidate, cacheSet } from "@/lib/queryCache";

interface Options {
  ttlMs?: number;
  enabled?: boolean;
}

/**
 * Returns cached data immediately, then refreshes in the background (SWR).
 */
export function useCachedQuery<T>(
  key: string,
  fetcher: () => Promise<T>,
  { ttlMs = 120_000, enabled = true }: Options = {},
) {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const [data, setData] = useState<T | null>(() => cacheGet<T>(key));
  const [loading, setLoading] = useState(() => cacheGet<T>(key) === null);
  const [refreshing, setRefreshing] = useState(false);
  const seqRef = useRef(0);

  const run = useCallback(
    async (background: boolean) => {
      const seq = ++seqRef.current;
      if (!background) {
        if (cacheGet<T>(key)) setRefreshing(true);
        else setLoading(true);
      }

      try {
        const fresh = await fetcherRef.current();
        if (seq !== seqRef.current) return;
        cacheSet(key, fresh, ttlMs);
        setData(fresh);
      } finally {
        if (seq === seqRef.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [key, ttlMs],
  );

  const refresh = useCallback(
    (force = true) => {
      if (force) cacheInvalidate(key);
      return run(false);
    },
    [key, run],
  );

  useEffect(() => {
    if (!enabled) return;
    const cached = cacheGet<T>(key);
    if (cached) {
      setData(cached);
      setLoading(false);
      run(true);
    } else {
      run(false);
    }
    return () => {
      seqRef.current += 1;
    };
  }, [key, enabled, run]);

  return { data, loading, refreshing, refresh, setData };
}
