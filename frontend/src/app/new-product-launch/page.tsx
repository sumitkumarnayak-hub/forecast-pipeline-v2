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
  new_product_launch_sheet_url: string | null;
  ff_automation_sheet_url: string | null;
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

      {/* New Product Launch Sheet button */}
      {info?.new_product_launch_sheet_url && (
        <a
          href={info.new_product_launch_sheet_url}
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
          New Product Launch
        </a>
      )}

      {/* FF Automation Sheet button */}
      {info?.ff_automation_sheet_url && (
        <a
          href={info.ff_automation_sheet_url}
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
          FF Automation
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
      {/* ── About banner ─────────────────────────────────────────── */}
      <div style={{
        background: "var(--indigo-dim, rgba(99,102,241,0.08))",
        border: "1px solid rgba(99,102,241,0.25)",
        borderRadius: "14px",
        padding: "1.1rem 1.4rem",
        marginBottom: "1.25rem",
        display: "flex",
        gap: "1rem",
        alignItems: "flex-start",
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: "10px",
          background: "rgba(99,102,241,0.15)",
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}>
          <ExternalLink size={16} style={{ color: "var(--indigo, #6366f1)" }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ margin: "0 0 0.3rem", fontWeight: 700, fontSize: "0.88rem", color: "var(--text-primary)" }}>
            Product Launch Module
          </p>
          <p style={{ margin: "0 0 0.65rem", fontSize: "0.78rem", color: "var(--text-secondary)", lineHeight: 1.55 }}>
            This module manages the end-to-end lifecycle of new product introductions, expansions and SKU replacements across hubs.
            Submissions go through a structured 4-stage wizard — upload, hub-split review, launch date selection, and final confirmation —
            before being logged to the <strong>Submission_Log</strong> sheet. Approved entries are automatically appended to the
            <strong> Launch_Output</strong> sheet for downstream planning.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {[
              { step: "1", label: "Pick tab", desc: "Choose New Launch, Expansion, or Replacement" },
              { step: "2", label: "Upload template", desc: "Download & fill the city or hub-level template" },
              { step: "3", label: "Review hub split", desc: "Auto-split or adjust per-hub quantities" },
              { step: "4", label: "Set launch date", desc: "Pick a valid Monday ≥ T+4" },
              { step: "5", label: "Submit", desc: "Confirm & send to Submission_Log for approval" },
            ].map(s => (
              <div key={s.step} style={{
                display: "flex", alignItems: "center", gap: "0.45rem",
                background: "var(--bg-elevated)", border: "1px solid var(--border)",
                borderRadius: "8px", padding: "0.3rem 0.65rem", fontSize: "0.71rem",
              }}>
                <span style={{
                  width: 18, height: 18, borderRadius: "50%",
                  background: "var(--indigo, #6366f1)", color: "#fff",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontWeight: 800, fontSize: "0.6rem", flexShrink: 0,
                }}>{s.step}</span>
                <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>{s.label}</span>
                <span style={{ color: "var(--text-muted)" }}>— {s.desc}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Tabs: child tabs promoted to top level ────────────────── */}
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
