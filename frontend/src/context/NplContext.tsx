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
      const [ctx, prods] = await Promise.all([loadNplContext({ force: true }), loadNplProductIds()]);
      setContext(ctx);
      setProducts(prods);
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
        const [ctx, prods] = await Promise.all([loadNplContext(), loadNplProductIds()]);
        if (!cancelled) {
          setContext(ctx);
          setProducts(prods);
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
