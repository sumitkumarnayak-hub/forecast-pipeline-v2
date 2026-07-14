"use client";

import { Suspense, useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { UrlTabs } from "@/components/ui/UrlTabs";
import { NplProvider } from "@/context/NplContext";
import NplWizard from "@/components/npl/NplWizard";
import SubmissionHistory from "@/components/npl/SubmissionHistory";
import SyncPhTab from "@/components/npl/SyncPhTab";
import AutoSyncTab from "@/components/npl/AutoSyncTab";
import api from "@/lib/api";
import { ExternalLink, Clock } from "lucide-react";

interface NplInfo {
  npl_sheet_url: string | null;
  ph_master_sheet_url: string | null;
  last_synced: string | null;
}

function NplHeaderActions() {
  const [info, setInfo] = useState<NplInfo | null>(null);

  useEffect(() => {
    api.get<NplInfo>("/api/new-product-launch/info")
      .then(({ data }) => setInfo(data))
      .catch(() => {});
  }, []);

  const formatLastSynced = (iso: string | null) => {
    if (!iso) return "Never synced";
    try {
      const d = new Date(iso);
      return d.toLocaleString("en-IN", {
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
      {/* Last synced badge */}
      <div style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.35rem",
        padding: "0.28rem 0.65rem",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "999px",
        fontSize: "0.71rem",
        color: "var(--text-muted)",
        fontWeight: 500,
        whiteSpace: "nowrap",
      }}>
        <Clock size={11} />
        Last synced:&nbsp;
        <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
          {info ? formatLastSynced(info.last_synced) : "—"}
        </span>
      </div>

      {/* NPL Sheet button */}
      {info?.npl_sheet_url && (
        <a
          href={info.npl_sheet_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.35rem",
            padding: "0.28rem 0.65rem",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            fontSize: "0.71rem",
            color: "var(--text-secondary)",
            fontWeight: 500,
            textDecoration: "none",
            cursor: "pointer",
            transition: "background 0.15s, border-color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
          onMouseLeave={e => (e.currentTarget.style.background = "var(--bg-elevated)")}
        >
          <ExternalLink size={11} />
          Launch Output
        </a>
      )}

      {/* P-H Master Sheet button */}
      {info?.ph_master_sheet_url && (
        <a
          href={info.ph_master_sheet_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.35rem",
            padding: "0.28rem 0.65rem",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            fontSize: "0.71rem",
            color: "var(--text-secondary)",
            fontWeight: 500,
            textDecoration: "none",
            cursor: "pointer",
            transition: "background 0.15s, border-color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
          onMouseLeave={e => (e.currentTarget.style.background = "var(--bg-elevated)")}
        >
          <ExternalLink size={11} />
          P-H Master Sheet
        </a>
      )}
    </div>
  );
}

function NewProductLaunchContent() {
  return (
    <AppShell
      title="Product Launch"
      subtitle="Launch planning, P-H sync, and automated new-product integration"
      actions={<NplHeaderActions />}
    >
      <UrlTabs
        defaultTab="launch"
        keepMounted={false}
        tabs={[
          {
            id: "launch",
            label: "Launch Planning",
            content: (
              <NplProvider>
                <UrlTabs
                  param="type"
                  defaultTab="type1"
                  keepMounted={false}
                  tabs={[
                    {
                      id: "type1",
                      label: "New Product Launch",
                      content: (
                        <NplWizard
                          key="new-launch"
                          subType="New Launch"
                          title="New Product Launch"
                          description="4-stage wizard — category, template, hub split, launch date, submit to Launch_Output."
                        />
                      ),
                    },
                    {
                      id: "type2",
                      label: "Product Expansion",
                      content: (
                        <NplWizard
                          key="expansion"
                          subType="Expansion"
                          title="Product Expansion"
                          description="Existing SKU expanding to new cities — same 4-stage flow with Expansion submission type."
                        />
                      ),
                    },
                    {
                      id: "type3",
                      label: "Product Replacement",
                      content: (
                        <NplWizard
                          key="replacement"
                          subType="Replacement"
                          title="Product Replacement"
                          description="Replace old SKU with new — upload hub-level plan and submit as Replacement."
                        />
                      ),
                    },
                    { id: "history", label: "Submission History", content: <SubmissionHistory /> },
                  ]}
                />
              </NplProvider>
            ),
          },
          /* { id: "sync-ph", label: "Sync to P-H Master", content: <SyncPhTab /> }, */
          /* { id: "auto-sync", label: "Auto Sync", content: <AutoSyncTab /> }, */
        ]}
      />
    </AppShell>
  );
}

export default function NewProductLaunchPage() {
  return (
    <Suspense>
      <NewProductLaunchContent />
    </Suspense>
  );
}
