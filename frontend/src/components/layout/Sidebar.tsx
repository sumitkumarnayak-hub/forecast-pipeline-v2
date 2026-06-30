"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearAuth } from "@/lib/auth";
import { useAuth } from "@/hooks/useAuth";
import { SIDEBAR_NAV, type NavEntry, type NavLink } from "@/lib/navigation";
import { ChevronDown, ChevronRight, Lock, LogOut } from "lucide-react";

const ROLE_BADGE: Record<string, string> = {
  admin: "Administrator",
  planner: "Planner",
  viewer: "Viewer",
};

function SidebarLink({
  item,
  active,
  locked,
  indent,
}: {
  item: NavLink;
  active: boolean;
  locked?: boolean;
  indent?: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={locked ? "#" : item.href}
      className={`nav-item${active ? " active" : ""}${locked ? " locked" : ""}`}
      style={indent ? { paddingLeft: "1.75rem", fontSize: "0.82rem" } : undefined}
      title={locked ? "Unlocks after baseline approval" : item.label}
    >
      <Icon className="nav-icon" size={indent ? 14 : 16} />
      {item.label}
      {locked && <Lock size={10} style={{ marginLeft: "auto", opacity: 0.5 }} />}
    </Link>
  );
}

export default function Sidebar({ baselineApproved }: { baselineApproved?: boolean }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, role, hydrated } = useAuth();
  const effectiveRole = hydrated ? role : "viewer";

  const baselineOpenDefault = pathname.startsWith("/baseline");
  const [baselineOpen, setBaselineOpen] = useState(baselineOpenDefault);

  useEffect(() => {
    if (pathname.startsWith("/baseline")) setBaselineOpen(true);
  }, [pathname]);

  const handleLogout = () => {
    clearAuth();
    router.replace("/login");
  };

  const isLinkActive = (item: NavLink) => {
    if (item.href.startsWith("/baseline/")) {
      return pathname === item.href;
    }
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  };

  const visibleEntries = SIDEBAR_NAV.filter(entry => {
    if (entry.type === "link") return entry.roles.includes(effectiveRole);
    return entry.roles.includes(effectiveRole);
  });

  const renderEntry = (entry: NavEntry) => {
    if (entry.type === "link") {
      const locked =
        entry.lockUntilBaselineApproved && !baselineApproved && effectiveRole !== "admin";
      return (
        <SidebarLink
          key={entry.id}
          item={entry}
          active={isLinkActive(entry)}
          locked={locked}
        />
      );
    }

    const children = entry.children.filter(c => c.roles.includes(effectiveRole));
    if (!children.length) return null;

    const groupActive = children.some(c => isLinkActive(c));

    return (
      <div key={entry.id}>
        <button
          type="button"
          className="nav-item"
          style={{
            width: "calc(100% - 1rem)",
            fontWeight: 600,
            color: groupActive ? "var(--blue)" : "var(--text-secondary)",
          }}
          onClick={() => setBaselineOpen(v => !v)}
        >
          {baselineOpen ? (
            <ChevronDown className="nav-icon" size={14} />
          ) : (
            <ChevronRight className="nav-icon" size={14} />
          )}
          {entry.label}
        </button>
        {entry.caption && baselineOpen && (
          <div
            style={{
              fontSize: "0.65rem",
              color: "var(--text-muted)",
              padding: "0 1rem 0.35rem 2.1rem",
            }}
          >
            {entry.caption}
          </div>
        )}
        {baselineOpen &&
          children.map(child => (
            <SidebarLink
              key={child.id}
              item={child}
              active={isLinkActive(child)}
              indent
            />
          ))}
      </div>
    );
  };

  return (
    <aside className="app-sidebar animate-slide-left">
      <div className="sidebar-brand">
        <div className="sidebar-brand-label">Demand Planning</div>
        <div className="sidebar-brand-name">Planning Suite</div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem 0" }}>
        <div className="sidebar-section-label">Navigation</div>
        {visibleEntries.map(renderEntry)}
      </div>

      {hydrated && user && (
        <div className="sidebar-user">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
              marginBottom: "0.65rem",
            }}
          >
            <div
              style={{
                width: 30,
                height: 30,
                borderRadius: "50%",
                background: "var(--blue-dim)",
                border: "1px solid var(--border-accent)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.7rem",
                fontWeight: 700,
                color: "var(--blue)",
                flexShrink: 0,
              }}
            >
              {user.full_name?.charAt(0)?.toUpperCase() || user.username.charAt(0).toUpperCase()}
            </div>
            <div style={{ minWidth: 0 }}>
              <div className="sidebar-user-name truncate">{user.full_name || user.username}</div>
              <div className="sidebar-user-role">{ROLE_BADGE[effectiveRole] || effectiveRole}</div>
            </div>
          </div>
          <button className="btn btn-secondary w-full btn-sm" onClick={handleLogout}>
            <LogOut size={13} /> Sign Out
          </button>
        </div>
      )}
    </aside>
  );
}
