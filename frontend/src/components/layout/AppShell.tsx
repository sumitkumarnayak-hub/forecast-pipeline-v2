"use client";
import { useEffect, useState, ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "./Sidebar";
import { prefetchAllRoutes } from "@/lib/pagePrefetch";
import { fetchBaselineStatus, BASELINE_APPROVED_KEY } from "@/lib/baselineStatus";
import { cacheGet } from "@/lib/queryCache";
import { rolesForPath } from "@/lib/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "@/lib/theme";
import { Menu, Moon, Sun, X } from "lucide-react";

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
      <Sidebar
        baselineApproved={baselineApproved}
        mobileOpen={mobileNavOpen}
        onNavigate={() => setMobileNavOpen(false)}
      />
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
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}

export default function AppShell({ children, title, subtitle, actions }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, role, hydrated } = useAuth();
  const [baselineApproved, setBaselineApproved] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!hydrated) return;
    if (!user) {
      router.replace("/login");
      return;
    }

    const cached = cacheGet<boolean>(BASELINE_APPROVED_KEY);
    if (cached !== null) {
      setBaselineApproved(cached);
      void fetchBaselineStatus().then(setBaselineApproved).catch(() => {});
      return;
    }

    void fetchBaselineStatus()
      .then(setBaselineApproved)
      .catch(() => {});
  }, [hydrated, user, router]);

  useEffect(() => {
    if (!hydrated || !user || !role) return;
    const allowed = rolesForPath(pathname);
    if (allowed && !allowed.includes(role)) {
      router.replace("/dashboard");
    }
  }, [hydrated, pathname, role, user, router]);

  useEffect(() => {
    if (!hydrated || !user || !role) return;
    prefetchAllRoutes(role);
  }, [hydrated, role, user]);

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
