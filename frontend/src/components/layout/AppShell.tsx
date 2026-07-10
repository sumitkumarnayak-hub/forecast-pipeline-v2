"use client";
import { useEffect, useState, ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "./Sidebar";
import { prefetchAllRoutes } from "@/lib/pagePrefetch";
import { fetchBaselineStatus, BASELINE_APPROVED_KEY } from "@/lib/baselineStatus";
import { cacheGet } from "@/lib/queryCache";
import { rolesForPath, homePathForRole } from "@/lib/navigation";
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
  const [cacheOpen, setCacheOpen] = useState(false);
  const [cacheData, setCacheData] = useState<Array<{
    name: string;
    category: string;
    last_updated: string;
    fresh: boolean;
    frequency: string;
  }>>([]);
  const [loadingCache, setLoadingCache] = useState(false);

  const fetchCacheStatus = async () => {
    setLoadingCache(true);
    try {
      const response = await fetch("/api/new-product-launch/cache-status");
      if (response.ok) {
        const data = await response.json();
        setCacheData(data.cache_status || []);
      }
    } catch (err) {
      console.error("Failed to load cache status", err);
    } finally {
      setLoadingCache(false);
    }
  };

  useEffect(() => {
    if (cacheOpen) {
      fetchCacheStatus();
    }
  }, [cacheOpen]);

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
          <div className="app-header-actions" style={{ position: "relative" }}>
            {actions}
            
            {/* Cache Status Toggle Button */}
            <button
              type="button"
              onClick={() => setCacheOpen(!cacheOpen)}
              className={`btn btn-ghost btn-icon ${cacheOpen ? "active" : ""}`}
              style={{ color: cacheOpen ? "var(--blue)" : "inherit" }}
              title="Cache Statuses (TTL)"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-timer">
                <line x1="10" x2="14" y1="2" y2="2"/>
                <line x1="12" x2="12" y1="14" y2="11"/>
                <circle cx="12" cy="14" r="8"/>
              </svg>
            </button>

            {/* Cache Status Dropdown Panel */}
            {cacheOpen && (
              <div 
                className="card shadow-lg" 
                style={{
                  position: "absolute",
                  top: "100%",
                  right: 0,
                  marginTop: "8px",
                  zIndex: 1000,
                  width: "360px",
                  maxHeight: "440px",
                  overflowY: "auto",
                  padding: "1rem",
                  background: "var(--bg-card, #151f32)",
                  border: "1px solid var(--border, #2d3c55)",
                  borderRadius: "12px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem", borderBottom: "1px solid var(--border, #2d3c55)", paddingBottom: "0.5rem" }}>
                  <span style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text-primary)" }}>Cache TTL Monitor</span>
                  <button 
                    type="button" 
                    className="btn btn-ghost btn-sm" 
                    onClick={fetchCacheStatus} 
                    disabled={loadingCache}
                    style={{ padding: "2px 6px", fontSize: "0.7rem", height: "auto" }}
                  >
                    {loadingCache ? "Refreshing..." : "Refresh"}
                  </button>
                </div>
                {loadingCache && cacheData.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "1rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>Loading status...</div>
                ) : cacheData.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "1rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>No cached files found.</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
                    {cacheData.map((item, idx) => (
                      <div 
                        key={idx} 
                        style={{ 
                          display: "flex", 
                          flexDirection: "column", 
                          gap: "0.2rem", 
                          padding: "0.5rem", 
                          borderRadius: "6px", 
                          background: "rgba(255,255,255,0.03)", 
                          borderLeft: `3px solid ${item.fresh ? "var(--green, #10b981)" : "var(--yellow, #f59e0b)"}`
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontWeight: 600, fontSize: "0.78rem", color: "var(--text-primary)" }}>{item.name}</span>
                          <span 
                            style={{ 
                              fontSize: "0.65rem", 
                              padding: "1px 5px", 
                              borderRadius: "4px", 
                              fontWeight: 600,
                              background: item.fresh ? "var(--green-dim)" : "var(--yellow-dim)", 
                              color: item.fresh ? "var(--green)" : "var(--yellow)" 
                            }}
                          >
                            {item.fresh ? "Fresh" : "Stale"}
                          </span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem", color: "var(--text-secondary)" }}>
                          <span>Updated: <strong style={{ color: "var(--text-primary)" }}>{item.last_updated}</strong></span>
                          <span>TTL: <strong>{item.frequency}</strong></span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

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
      router.replace(homePathForRole(role));
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
