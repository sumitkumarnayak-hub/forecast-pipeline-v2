"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getUser, clearAuth, canWrite, isAdmin } from "@/lib/auth";
import {
  LayoutDashboard, Database, BarChart2, Zap, ClipboardList,
  Package, LineChart, Settings, LogOut, Lock
} from "lucide-react";

const NAV = [
  { label: "Dashboard",        href: "/dashboard",           icon: LayoutDashboard, roles: ["admin","planner","viewer"] },
  { label: "Baseline",         href: "/baseline",            icon: BarChart2,        roles: ["admin","planner"] },
  { label: "Auto-Pilot",       href: "/autopilot",           icon: Zap,              roles: ["admin","planner"] },
  { label: "Master Data",      href: "/master-data",         icon: Database,         roles: ["admin","planner","viewer"] },
  { label: "Final Plan",       href: "/final-plan",          icon: ClipboardList,    roles: ["admin","planner"] },
  { label: "Product Launch",   href: "/new-product-launch",  icon: Package,          roles: ["admin","planner"] },
  { label: "Analytics",        href: "/analytics",           icon: LineChart,        roles: ["admin","planner","viewer"] },
  { label: "Settings",         href: "/settings",            icon: Settings,         roles: ["admin","planner","viewer"] },
];

const ROLE_BADGE: Record<string,string> = { admin: "Admin", planner: "Planner", viewer: "Viewer" };

export default function Sidebar({ baselineApproved }: { baselineApproved?: boolean }) {
  const pathname = usePathname();
  const router = useRouter();
  const user = getUser();
  const role = user?.role || "viewer";

  const handleLogout = () => {
    clearAuth();
    router.replace("/login");
  };

  const visibleNav = NAV.filter(n => n.roles.includes(role));

  return (
    <aside className="app-sidebar animate-slide-left">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-label">Demand Planning</div>
        <div className="sidebar-brand-name">Planning Suite</div>
      </div>

      {/* Nav */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem 0" }}>
        <div className="sidebar-section-label">Navigation</div>
        {visibleNav.map(item => {
          const Icon = item.icon;
          const active = pathname.startsWith(item.href);
          const locked = item.href === "/final-plan" && !baselineApproved && role !== "admin";
          return (
            <Link
              key={item.href}
              href={locked ? "#" : item.href}
              className={`nav-item${active ? " active" : ""}${locked ? " locked" : ""}`}
              title={locked ? "Unlocks after baseline approval" : item.label}
            >
              <Icon className="nav-icon" size={16} />
              {item.label}
              {locked && <Lock size={10} style={{ marginLeft: "auto", opacity: 0.5 }} />}
            </Link>
          );
        })}
      </div>

      {/* User panel */}
      {user && (
        <div className="sidebar-user">
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.65rem" }}>
            <div style={{
              width: 30, height: 30, borderRadius: "50%",
              background: "var(--blue-dim)", border: "1px solid var(--border-accent)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: "0.7rem", fontWeight: 700, color: "var(--blue)", flexShrink: 0
            }}>
              {user.full_name?.charAt(0)?.toUpperCase() || user.username.charAt(0).toUpperCase()}
            </div>
            <div style={{ minWidth: 0 }}>
              <div className="sidebar-user-name truncate">{user.full_name || user.username}</div>
              <div className="sidebar-user-role">{ROLE_BADGE[role] || role}</div>
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
