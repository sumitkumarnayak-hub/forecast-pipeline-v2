"use client";

import {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AppTheme = "light" | "dark";

const STORAGE_KEY = "ps-theme";

interface ThemeContextValue {
  theme: AppTheme;
  resolvedTheme: AppTheme;
  setTheme: (theme: AppTheme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyTheme(theme: AppTheme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.classList.remove("light", "dark");
  root.classList.add(theme);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>("light");

  useLayoutEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    const initial: AppTheme = stored === "dark" ? "dark" : "light";
    setThemeState(initial);
    applyTheme(initial);
  }, []);

  const setTheme = useCallback((next: AppTheme) => {
    setThemeState(next);
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }, []);

  const value = useMemo(
    () => ({ theme, resolvedTheme: theme, setTheme }),
    [theme, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    return {
      theme: "light" as AppTheme,
      resolvedTheme: "light" as AppTheme,
      setTheme: () => {},
    };
  }
  return ctx;
}
