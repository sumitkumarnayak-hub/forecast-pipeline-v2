"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  loadNplContext,
  loadNplProductIds,
  loadNplProductsByCategory,
  peekNplContext,
  loadNplBootstrap,
  type NplContextData,
  type NplProductRow,
} from "@/lib/nplBootstrap";

type NplContextValue = {
  context: NplContextData | null;
  products: NplProductRow[];
  loading: boolean;
  error: string | null;
  getProductsByCategory: (category: string) => Promise<string[]>;
  refresh: () => Promise<void>;
};

const NplContext = createContext<NplContextValue | null>(null);

export function NplProvider({ children }: { children: ReactNode }) {
  const [context, setContext] = useState<NplContextData | null>(() => peekNplContext());
  const [products, setProducts] = useState<NplProductRow[]>([]);
  const [loading, setLoading] = useState(() => !peekNplContext());
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await loadNplBootstrap({ force: true });
      setContext({
        categories: data.categories,
        cities: data.cities,
        earliest_launch_date: data.earliest_launch_date,
      });
      setProducts(data.products || []);
      setError(null);
    } catch {
      setError("Could not load launch master data. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const hadCache = Boolean(peekNplContext());
    (async () => {
      try {
        const data = await loadNplBootstrap();
        if (!cancelled) {
          setContext({
            categories: data.categories,
            cities: data.cities,
            earliest_launch_date: data.earliest_launch_date,
          });
          setProducts(data.products || []);
          setError(null);
        }
      } catch {
        if (!cancelled && !hadCache) {
          setError("Could not load launch master data. Check your connection and try again.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({
      context,
      products,
      loading,
      error,
      getProductsByCategory: loadNplProductsByCategory,
      refresh,
    }),
    [context, products, loading, error, refresh],
  );

  return <NplContext.Provider value={value}>{children}</NplContext.Provider>;
}

export function useNplBootstrap() {
  const ctx = useContext(NplContext);
  if (!ctx) throw new Error("useNplBootstrap must be used within NplProvider");
  return ctx;
}
