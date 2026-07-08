"use client";

import { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { RefreshCw, CheckCircle2, XCircle, Info, Landmark } from "lucide-react";

export default function HubLaunchTab() {
  const { canWrite } = useAuth();
  const [newHub, setNewHub] = useState("");
  const [sourceHub, setSourceHub] = useState("");
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [report, setReport] = useState<{ rows_inserted: number; duplicates_skipped: number } | null>(null);

  // List of active reference source hubs from planning catalog configuration
  const sourceHubOptions = [
    "NDM", "NDH", "TUB", "BEG", "KLK", "KML", "KPL", "CHE", "HYD", "BLR", "MUM"
  ];

  const handleSync = async () => {
    if (!newHub.trim()) {
      setMsg({ text: "Please enter the new destination Hub name.", type: "warning" });
      return;
    }
    if (!sourceHub) {
      setMsg({ text: "Please select a reference Source Hub.", type: "warning" });
      return;
    }
    setRunning(true);
    setMsg({ text: "", type: "" });
    setReport(null);
    try {
      const { data } = await api.post("/api/new-product-launch/sync-new-hub", {
        new_hub: newHub.trim().toUpperCase(),
        source_hub: sourceHub.trim().toUpperCase(),
      });
      setReport(data);
      setMsg({ text: data.detail || "Hub sync completed successfully.", type: "success" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Sync failed", type: "danger" });
    } finally {
      setRunning(false);
    }
  };

  return (
    <div style={{ maxWidth: 640 }}>
      {/* Info card */}
      <div style={{
        display: "flex",
        gap: "0.75rem",
        padding: "0.85rem 1rem",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "8px",
        marginBottom: "1.25rem",
        fontSize: "0.8rem",
        color: "var(--text-muted)",
        lineHeight: 1.5,
      }}>
        <Info size={15} style={{ flexShrink: 0, marginTop: 2, color: "var(--accent)" }} />
        <div>
          <strong style={{ color: "var(--text-primary)" }}>New Hub Launch Sync</strong> — Clones existing active
          mappings from a reference source hub to the new destination hub.
          <div style={{ marginTop: "0.35rem" }}>
            Ensure <code>Hub_name</code> is configured in the **Hub Mapping** tab first before triggering the sync.
          </div>
        </div>
      </div>

      {/* Alert */}
      {msg.text && (
        <div className={`alert alert-${msg.type} mb-4`} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {msg.type === "success" ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
          {msg.text}
        </div>
      )}

      {/* Form elements */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginBottom: "1.5rem" }}>
        <div>
          <label className="text-sm" style={{ display: "block", fontWeight: 600, marginBottom: "0.4rem", color: "var(--text-secondary)" }}>
            New Hub Name *
          </label>
          <input
            type="text"
            className="form-input text-sm"
            placeholder="e.g. NDM_NEW"
            value={newHub}
            onChange={e => setNewHub(e.target.value)}
            disabled={!canWrite || running}
          />
        </div>

        <div>
          <label className="text-sm" style={{ display: "block", fontWeight: 600, marginBottom: "0.4rem", color: "var(--text-secondary)" }}>
            Source Reference Hub *
          </label>
          <select
            className="form-input text-sm"
            value={sourceHub}
            onChange={e => setSourceHub(e.target.value)}
            disabled={!canWrite || running}
          >
            <option value="">Select source hub</option>
            {sourceHubOptions.map(h => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Action button */}
      <button
        className="btn btn-primary btn-sm w-full"
        onClick={handleSync}
        disabled={!canWrite || running}
        style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem", height: "2.2rem" }}
      >
        {running ? (
          <>
            <RefreshCw size={14} className="animate-spin" />
            Cloning and Syncing rows...
          </>
        ) : (
          <>
            <Landmark size={14} />
            Sync New Hubs to P-H Master
          </>
        )}
      </button>

      {/* Sync Report */}
      {report && (
        <div className="card mt-4" style={{ padding: "1.25rem" }}>
          <h5 style={{ margin: "0 0 0.75rem", fontSize: "0.9rem", fontWeight: 700 }}>Sync Summary Report</h5>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div style={{ padding: "0.75rem", background: "var(--bg-hover)", borderRadius: 6, textAlign: "center" }}>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--accent)" }}>{report.rows_inserted}</div>
              <div className="text-xs text-muted mt-1">Rows Inserted</div>
            </div>
            <div style={{ padding: "0.75rem", background: "var(--bg-hover)", borderRadius: 6, textAlign: "center" }}>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-secondary)" }}>{report.duplicates_skipped}</div>
              <div className="text-xs text-muted mt-1">Duplicates Skipped</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
