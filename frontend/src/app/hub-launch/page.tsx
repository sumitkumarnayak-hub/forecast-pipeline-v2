"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import HubLaunchTab from "@/components/npl/HubLaunchTab";
import api from "@/lib/api";
import { ExternalLink } from "lucide-react";

interface NplInfo {
  ff_input_sheet_url: string | null;
  hub_mapping_sheet_url: string | null;
  hub_sku_sheet_url: string | null;
  last_synced: string | null;
}

function HubLaunchHeaderActions() {
  const [info, setInfo] = useState<NplInfo | null>(null);

  useEffect(() => {
    api.get<NplInfo>("/api/new-product-launch/info")
      .then(({ data }) => setInfo(data))
      .catch(() => {});
  }, []);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
      {/* FF Input Sheet button */}
      {info?.ff_input_sheet_url && (
        <a
          href={info.ff_input_sheet_url}
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
          FF Input
        </a>
      )}

      {/* Hub Mapping sheet (dedicated env: HUB_MAPPING_SHEET_URL) */}
      {info?.hub_mapping_sheet_url && (
        <a
          href={info.hub_mapping_sheet_url}
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
          Hub Mapping
        </a>
      )}
    </div>
  );
}

export default function HubLaunchPage() {
  return (
    <AppShell
      title="Hub Launch"
      subtitle="Configure new hub mappings by cloning rows from reference source hubs"
      actions={<HubLaunchHeaderActions />}
    >
      <div className="card" style={{ padding: "1.5rem" }}>
        <HubLaunchTab />
      </div>
    </AppShell>
  );
}
