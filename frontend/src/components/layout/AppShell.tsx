"use client";
import { useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated, getUser } from "@/lib/auth";
import Sidebar from "./Sidebar";
import api from "@/lib/api";

import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";

interface Props {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
}

export default function AppShell({ children, title, subtitle, actions }: Props) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [baselineApproved, setBaselineApproved] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    if (!isAuthenticated()) { router.replace("/login"); return; }
    setMounted(true);
    api.get("/api/baseline/status").then(r => setBaselineApproved(r.data.approved)).catch(() => {});
  }, [router]);

  if (!mounted) return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-base)" }}>
      <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
    </div>
  );

  return (
    <div className="app-shell">
      <Sidebar baselineApproved={baselineApproved} />
      <div className="app-main">
        <header className="app-header">
          <div style={{ flex: 1 }}>
            {title && <h1 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>{title}</h1>}
            {subtitle && <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.1rem" }}>{subtitle}</div>}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
            {actions}
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="btn btn-secondary"
              style={{ padding: "0.4rem" }}
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </header>
        <main className="app-content animate-fade-in">{children}</main>
      </div>
    </div>
  );
}
