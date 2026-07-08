"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { logout } from "@/lib/auth";
import { useAuth } from "@/hooks/useAuth";
import { SIDEBAR_NAV, type NavEntry, type NavLink } from "@/lib/navigation";
import DemoFilterPanel from "./DemoFilterPanel";
import { prefetchRoute } from "@/lib/pagePrefetch";
import { ChevronDown, ChevronRight, LogOut, LayoutGrid } from "lucide-react";

const ROLE_BADGE: Record<string, string> = {
  admin: "Administrator",
  planner: "Planner",
  viewer: "Viewer",
  product: "Product",
};

function SidebarLink({
  item,
  active,
  child,
  onNavigate,
}: {
  item: NavLink;
  active: boolean;
  child?: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      prefetch
      onMouseEnter={() => prefetchRoute(item.href)}
      onFocus={() => prefetchRoute(item.href)}
      onClick={() => {
        prefetchRoute(item.href);
        onNavigate?.();
      }}
      className={`nav-item${active ? " active" : ""}${child ? " nav-item-child" : ""}`}
    >
      <span className="nav-item-icon">
        <Icon size={child ? 15 : 17} strokeWidth={active ? 2.25 : 2} />
      </span>
      <span className="nav-item-label">{item.label}</span>
    </Link>
  );
}

export default function Sidebar({
  baselineApproved,
  mobileOpen,
  onNavigate,
}: {
  baselineApproved?: boolean;
  mobileOpen?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, role, hydrated } = useAuth();
  const effectiveRole = hydrated ? role : "viewer";

  const baselineOpenDefault = pathname.startsWith("/baseline");
  const [baselineOpen, setBaselineOpen] = useState(baselineOpenDefault);

  useEffect(() => {
    if (pathname.startsWith("/baseline")) setBaselineOpen(true);
  }, [pathname]);

  const handleLogout = async () => {
    await logout();
    router.replace("/login");
  };

  const isLinkActive = (item: NavLink) => {
    if (item.href.startsWith("/baseline/")) {
      return pathname === item.href;
    }
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  };

  const visibleEntries = SIDEBAR_NAV.filter(entry => entry.roles.includes(effectiveRole));

  const renderEntry = (entry: NavEntry) => {
    if (entry.type === "link") {
      if (entry.lockUntilBaselineApproved && !baselineApproved) {
        return null;
      }
      return (
        <SidebarLink key={entry.id} item={entry} active={isLinkActive(entry)} onNavigate={onNavigate} />
      );
    }

    const children = entry.children.filter(c => c.roles.includes(effectiveRole));
    if (!children.length) return null;

    const groupActive = children.some(c => isLinkActive(c));

    return (
      <div key={entry.id} className="nav-group">
        <button
          type="button"
          className={`nav-group-toggle${groupActive ? " is-active" : ""}`}
          onClick={() => setBaselineOpen(v => !v)}
          aria-expanded={baselineOpen}
        >
          <span className="nav-group-chevron">
            {baselineOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
          <span className="nav-group-label">{entry.label}</span>
        </button>
        {entry.caption && baselineOpen && (
          <p className="nav-group-caption">{entry.caption}</p>
        )}
        {baselineOpen && (
          <div className="nav-sublist">
            {children.map(child => (
              <SidebarLink
                key={child.id}
                item={child}
                active={isLinkActive(child)}
                child
                onNavigate={onNavigate}
              />
            ))}
          </div>
        )}
      </div>
    );
  };

  const initials =
    user?.full_name?.charAt(0)?.toUpperCase() ||
    user?.email?.charAt(0)?.toUpperCase() ||
    "?";

  return (
    <aside className={`app-sidebar${mobileOpen ? " is-open" : ""}`}>
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark" aria-hidden>
          <LayoutGrid size={18} strokeWidth={2.25} />
        </div>
        <div className="sidebar-brand-text">
          <span className="sidebar-brand-name">Planning Suite</span>
          <span className="sidebar-brand-tag">Demand Planning</span>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Main navigation">
        <p className="sidebar-section-label">Menu</p>
        <div className="sidebar-nav-list">{visibleEntries.map(renderEntry)}</div>
      </nav>

      <DemoFilterPanel />

      {hydrated && user && (
        <footer className="sidebar-footer">
          <div className="sidebar-user-card">
            <div className="sidebar-avatar" aria-hidden>
              {initials}
            </div>
            <div className="sidebar-user-meta">
              <span className="sidebar-user-name truncate">{user.full_name || user.email}</span>
              <span className="sidebar-user-role">{ROLE_BADGE[effectiveRole] || effectiveRole}</span>
            </div>
          </div>
          <button type="button" className="sidebar-logout-btn" onClick={handleLogout}>
            <LogOut size={15} />
            Sign out
          </button>
        </footer>
      )}
    </aside>
  );

}
