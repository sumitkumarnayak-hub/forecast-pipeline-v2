"use client";
import { Suspense, useEffect, useState, ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchSession } from "@/lib/auth";
import Sidebar from "./Sidebar";
import api from "@/lib/api";
import { cacheGet, cacheSet } from "@/lib/queryCache";
import { rolesForPath } from "@/lib/navigation";
import { useAuth } from "@/hooks/useAuth";
import { prefetchAllRoutes } from "@/lib/pagePrefetch";

import { useTheme } from "@/lib/theme";
import { Menu, Moon, Sun, X } from "lucide-react";

const BASELINE_APPROVED_KEY = "shell:baseline-approved";

interface Props {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
}

function ShellFrame({
  children,
  title,
  subtitle,
  actions,
  baselineApproved,
  theme,
  setTheme,
  mobileNavOpen,
  setMobileNavOpen,
}: Props & {
  baselineApproved: boolean;
  theme: "light" | "dark";
  setTheme: (t: "light" | "dark") => void;
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;
}) {
  return (
    <div className="app-shell">
      {mobileNavOpen && (
        <button
          type="button"
          className="mobile-nav-backdrop"
          aria-label="Close navigation menu"
          onClick={() => setMobileNavOpen(false)}
        />
      )}
      <Suspense fallback={<aside className="app-sidebar" />}>
        <Sidebar
          baselineApproved={baselineApproved}
          mobileOpen={mobileNavOpen}
          onNavigate={() => setMobileNavOpen(false)}
        />
      </Suspense>
      <div className="app-main">
        <header className="app-header">
          <div className="app-header-start">
            <button
              type="button"
              className="btn btn-ghost btn-icon mobile-menu-btn"
              aria-label={mobileNavOpen ? "Close menu" : "Open menu"}
              aria-expanded={mobileNavOpen}
              onClick={() => setMobileNavOpen(!mobileNavOpen)}
            >
              {mobileNavOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <div className="app-header-text">
              {title && <h1 className="app-header-title">{title}</h1>}
              {subtitle && <p className="app-header-sub">{subtitle}</p>}
            </div>
          </div>
          <div className="app-header-actions">
            {actions}
            <button
              type="button"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="btn btn-ghost btn-icon"
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </header>
        <main className="app-content animate-fade-in">{children}</main>
      </div>
    </div>
  );
}

export default function AppShell({ children, title, subtitle, actions }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const { role, hydrated: authHydrated } = useAuth();
  const [mounted, setMounted] = useState(false);
  const [authed, setAuthed] = useState(true);
  const [baselineApproved, setBaselineApproved] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    let cancelled = false;
    void fetchSession().then((user) => {
      if (cancelled) return;
      const ok = !!user;
      setAuthed(ok);
      setMounted(true);

      const cached = cacheGet<boolean>(BASELINE_APPROVED_KEY);
      if (cached !== null) setBaselineApproved(cached);

      if (!ok) {
        router.replace("/login");
        return;
      }

      api
        .get("/api/baseline/status")
        .then(r => {
          const approved = Boolean(r.data.approved);
          setBaselineApproved(approved);
          cacheSet(BASELINE_APPROVED_KEY, approved, 300_000);
        })
        .catch(() => {});
    });

    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    if (!authHydrated || !role) return;
    const allowed = rolesForPath(pathname);
    if (allowed && role && !allowed.includes(role)) {
      router.replace("/dashboard");
    }
  }, [authHydrated, pathname, role, router]);

  useEffect(() => {
    if (!authHydrated || !role) return;
    prefetchAllRoutes(role);
  }, [authHydrated, role]);

  if (!mounted) {
    return (
      <ShellFrame
        title={title}
        subtitle={subtitle}
        actions={actions}
        baselineApproved={false}
        theme="light"
        setTheme={() => {}}
        mobileNavOpen={false}
        setMobileNavOpen={() => {}}
      >
        {children}
      </ShellFrame>
    );
  }

  if (!authed) return null;

  return (
    <ShellFrame
      title={title}
      subtitle={subtitle}
      actions={actions}
      baselineApproved={baselineApproved}
      theme={theme}
      setTheme={setTheme}
      mobileNavOpen={mobileNavOpen}
      setMobileNavOpen={setMobileNavOpen}
    >
      {children}
    </ShellFrame>
  );
}
