"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import {
  readSessionBootstrapEntry,
  writeSessionBootstrap,
  BOOTSTRAP_TTL_MS,
} from "@/lib/bootstrapCache";

/**
 * Stale-while-revalidate: show cached bootstrap after mount, refresh when half-stale.
 */
export function useInstantBootstrap<T>(storageKey: string, url: string, ttlMs = BOOTSTRAP_TTL_MS) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const seq = useRef(0);
  const mounted = useRef(false);

  const fetchFresh = useCallback(
    async (opts?: { showLoading?: boolean }) => {
      const showLoading = opts?.showLoading ?? false;
      if (showLoading) setLoading(true);
      const n = ++seq.current;
      try {
        const { data: fresh } = await api.get<T>(url);
        if (n !== seq.current) return;
        setData(fresh);
        writeSessionBootstrap(storageKey, fresh);
        setError("");
      } catch (e: unknown) {
        if (n !== seq.current) return;
        const err = e as { response?: { data?: { detail?: string } } };
        if (!readSessionBootstrapEntry<T>(storageKey, ttlMs)) {
          setError(err?.response?.data?.detail || "Failed to load");
        }
      } finally {
        if (n === seq.current && showLoading) setLoading(false);
      }
    },
    [storageKey, url, ttlMs],
  );

  useEffect(() => {
    if (mounted.current) return;
    mounted.current = true;

    const cached = readSessionBootstrapEntry<T>(storageKey, ttlMs);
    if (cached) {
      setData(cached.data);
      setLoading(false);
      if (cached.ageMs > ttlMs * 0.5) {
        void fetchFresh();
      }
    } else {
      void fetchFresh({ showLoading: true });
    }
  }, [fetchFresh, storageKey, ttlMs]);

  const reload = useCallback(
    (force?: boolean) => {
      if (force) {
        try {
          sessionStorage.removeItem(storageKey);
        } catch {
          /* ignore */
        }
      }
      return fetchFresh({ showLoading: true });
    },
    [fetchFresh, storageKey],
  );

  return { data, setData, loading, error, reload };
}
