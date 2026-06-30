"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useCallback, useTransition } from "react";

export interface UrlTab {
  id: string;
  label: ReactNode;
  content: ReactNode;
}

interface UrlTabsProps {
  tabs: UrlTab[];
  /** Query param name — default `tab` */
  param?: string;
  defaultTab?: string;
  className?: string;
  /** Keep inactive panels mounted for instant tab switches (default true). */
  keepMounted?: boolean;
}

export function UrlTabs({
  tabs,
  param = "tab",
  defaultTab,
  className = "",
  keepMounted = true,
}: UrlTabsProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();
  const active = searchParams.get(param) || defaultTab || tabs[0]?.id;

  const select = useCallback(
    (id: string) => {
      if (id === active) return;
      const next = new URLSearchParams(searchParams.toString());
      next.set(param, id);
      startTransition(() => {
        router.replace(`${pathname}?${next.toString()}`, { scroll: false });
      });
    },
    [active, param, pathname, router, searchParams],
  );

  if (!tabs.length) return null;

  return (
    <div className={className} style={{ width: "100%", minWidth: 0, maxWidth: "100%" }}>
      <div
        className="tabs-scroll"
        style={{
          display: "flex",
          borderBottom: "1px solid var(--border)",
          gap: "0.5rem",
          marginBottom: "1.5rem",
          overflowX: "auto",
          whiteSpace: "nowrap",
          scrollbarWidth: "none",
        }}
      >
        {tabs.map(tab => {
          const isActive = active === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => select(tab.id)}
              style={{
                padding: "0.65rem 1.15rem",
                fontSize: "0.85rem",
                fontWeight: 600,
                background: "none",
                border: "none",
                cursor: "pointer",
                color: isActive ? "var(--blue)" : "var(--text-muted)",
                borderBottom: isActive ? "2px solid var(--blue)" : "2px solid transparent",
                marginBottom: "-1px",
                outline: "none",
                whiteSpace: "nowrap",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {keepMounted ? (
        <div>
          {tabs.map(tab => (
            <div
              key={tab.id}
              hidden={active !== tab.id}
              aria-hidden={active !== tab.id}
            >
              {tab.content}
            </div>
          ))}
        </div>
      ) : (
        <div>{tabs.find(t => t.id === active)?.content}</div>
      )}
    </div>
  );
}
