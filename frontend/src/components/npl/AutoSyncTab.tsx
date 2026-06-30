"use client";

import { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { PlayCircle } from "lucide-react";

export default function AutoSyncTab() {
  const { readOnly } = useAuth();
  const [pids, setPids] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [msg, setMsg] = useState({ text: "", type: "" });

  const runSync = async () => {
    setRunning(true);
    setMsg({ text: "", type: "" });
    const product_ids = pids.split(/[,\s]+/).map(s => s.trim()).filter(Boolean);
    try {
      const { data } = await api.post("/api/new-product-launch/auto-sync", { product_ids, dry_run: dryRun });
      setResult(data);
      setMsg({
        text: data.success
          ? `Sync OK — ${data.rows_inserted} rows inserted`
          : String(data.error || "Sync failed"),
        type: data.success ? "success" : "danger",
      });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Auto sync failed", type: "danger" });
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="card">
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>
        <PlayCircle size={15} style={{ display: "inline", marginRight: 6 }} />
        Run New Product Sync
      </div>
      {msg.text && <div className={`alert alert-${msg.type} mb-3 text-sm`}>{msg.text}</div>}
      <textarea
        className="form-input mb-3"
        rows={3}
        placeholder="Optional product IDs (leave blank for auto-discover)…"
        value={pids}
        onChange={e => setPids(e.target.value)}
        disabled={readOnly}
      />
      <label className="text-sm mb-3" style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} disabled={readOnly} />
        Dry run (validate only)
      </label>
      <button type="button" className="btn btn-primary" disabled={readOnly || running} onClick={runSync}>
        {running ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <PlayCircle size={14} />}
        {running ? "Running…" : dryRun ? "Validate sync" : "Run sync"}
      </button>
      {result && (
        <pre className="text-xs mt-4" style={{ background: "var(--bg-elevated)", padding: "0.75rem", borderRadius: 8, overflow: "auto" }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}
