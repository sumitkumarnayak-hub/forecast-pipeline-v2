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
  loadNplProductsByCategory,
  peekNplBootstrap,
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
  // Keep SSR and first client paint identical — never read sessionStorage in useState initializers.
  const [context, setContext] = useState<NplContextData | null>(null);
  const [products, setProducts] = useState<NplProductRow[]>([]);
  const [loading, setLoading] = useState(true);
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
    const cached = peekNplBootstrap();
    if (cached) {
      setContext({
        categories: cached.categories,
        cities: cached.cities,
        earliest_launch_date: cached.earliest_launch_date,
      });
      setProducts(cached.products || []);
      setLoading(false);
    }

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
        if (!cancelled && !cached) {
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
