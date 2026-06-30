"use client";
import { Suspense, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import Sidebar from "./Sidebar";
import api from "@/lib/api";
import { cacheGet, cacheSet } from "@/lib/queryCache";

import { useTheme } from "@/lib/theme";
import { Moon, Sun } from "lucide-react";

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
}: Props & {
  baselineApproved: boolean;
  theme: "light" | "dark";
  setTheme: (t: "light" | "dark") => void;
}) {
  return (
    <div className="app-shell">
      <Suspense fallback={<aside className="app-sidebar" />}>
        <Sidebar baselineApproved={baselineApproved} />
      </Suspense>
      <div className="app-main">
        <header className="app-header">
          <div style={{ flex: 1 }}>
            {title && (
              <h1
                style={{
                  fontSize: "0.95rem",
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  letterSpacing: "-0.01em",
                }}
              >
                {title}
              </h1>
            )}
            {subtitle && (
              <div
                style={{
                  fontSize: "0.75rem",
                  color: "var(--text-secondary)",
                  marginTop: "0.1rem",
                }}
              >
                {subtitle}
              </div>
            )}
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

export default function AppShell({ children, title, subtitle, actions }: Props) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [authed, setAuthed] = useState(true);
  const [baselineApproved, setBaselineApproved] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    const ok = isAuthenticated();
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
  }, [router]);

  if (!mounted) {
    return (
      <ShellFrame
        title={title}
        subtitle={subtitle}
        actions={actions}
        baselineApproved={false}
        theme="light"
        setTheme={() => {}}
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
    >
      {children}
    </ShellFrame>
  );
}
