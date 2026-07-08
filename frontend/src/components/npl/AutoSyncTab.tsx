"use client";

import { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { PlayCircle, CheckCircle2, XCircle, Info } from "lucide-react";

interface SyncResult {
  success: boolean;
  products_found: number;
  rows_inserted: number;
  duplicates_skipped: number;
  masters_re_synced: boolean;
  ph_rows_after: number;
  products_synced: string[];
  error: string;
  dry_run: boolean;
}

export default function AutoSyncTab() {
  const { canWrite } = useAuth();
  const [pids, setPids] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SyncResult | null>(null);
  const [msg, setMsg] = useState({ text: "", type: "" });

  const runSync = async () => {
    setRunning(true);
    setMsg({ text: "", type: "" });
    setResult(null);
    const product_ids = pids.split(/[,\s]+/).map(s => s.trim()).filter(Boolean);
    try {
      const { data } = await api.post<SyncResult>("/api/new-product-launch/auto-sync", { product_ids, dry_run: dryRun });
      setResult(data);
      setMsg({
        text: data.success
          ? dryRun
            ? `Dry run complete — ${data.products_found} products found, ${data.rows_inserted} rows would be inserted`
            : `Sync complete — ${data.rows_inserted} rows inserted, ${data.duplicates_skipped} duplicates skipped`
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
          <strong style={{ color: "var(--text-primary)" }}>Auto Sync</strong> scans the New Product Launch sheet and
          automatically inserts qualifying rows into the P-H Master.
          Leave product IDs blank to auto-discover all new products.
          Use <strong>dry run</strong> to preview changes without writing to the sheet.
        </div>
      </div>

      {/* Alert */}
      {msg.text && (
        <div className={`alert alert-${msg.type} mb-4`} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {msg.type === "success" ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
          {msg.text}
        </div>
      )}

      {/* Product IDs input */}
      <label className="text-sm" style={{ display: "block", fontWeight: 600, marginBottom: "0.4rem", color: "var(--text-secondary)" }}>
        Product IDs (optional)
      </label>
      <textarea
        className="form-input mb-1"
        rows={3}
        placeholder="Leave blank to auto-discover all new products, or enter specific IDs (comma or newline separated)…"
        value={pids}
        onChange={e => setPids(e.target.value)}
        disabled={!canWrite}
        style={{ resize: "vertical", fontFamily: "monospace", fontSize: "0.8rem" }}
      />
      <p className="text-xs text-muted mb-4">e.g. P001, P002, P003</p>

      {/* Dry run toggle */}
      <label style={{
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        cursor: canWrite ? "pointer" : "not-allowed",
        marginBottom: "1.25rem",
        padding: "0.65rem 1rem",
        background: dryRun ? "rgba(var(--accent-rgb, 99,102,241), 0.06)" : "var(--bg-elevated)",
        border: `1px solid ${dryRun ? "var(--accent)" : "var(--border)"}`,
        borderRadius: "8px",
        transition: "all 0.15s",
      }}>
        <input
          type="checkbox"
          checked={dryRun}
          onChange={e => setDryRun(e.target.checked)}
          disabled={!canWrite}
          style={{ accentColor: "var(--accent)", width: 15, height: 15 }}
        />
        <div>
          <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-primary)" }}>
            Dry run (validate only)
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            Preview what would be synced without writing to the sheet
          </div>
        </div>
      </label>

      {/* Run button */}
      <button
        type="button"
        className={`btn ${dryRun ? "btn-secondary" : "btn-primary"}`}
        disabled={!canWrite || running}
        onClick={runSync}
        style={{ minWidth: 160 }}
      >
        {running ? (
          <><span className="spinner" style={{ width: 14, height: 14 }} /> Running…</>
        ) : dryRun ? (
          <><PlayCircle size={14} /> Validate Sync</>
        ) : (
          <><PlayCircle size={14} /> Run Sync Now</>
        )}
      </button>

      {/* Results */}
      {result && (
        <div style={{
          marginTop: "1.5rem",
          padding: "1rem",
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: "10px",
        }}>
          <div style={{ fontWeight: 700, fontSize: "0.82rem", marginBottom: "0.85rem", color: "var(--text-primary)" }}>
            {result.dry_run ? "Dry Run Results" : "Sync Results"}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "0.75rem" }}>
            {[
              { label: "Products Found", value: result.products_found },
              { label: result.dry_run ? "Rows to Insert" : "Rows Inserted", value: result.rows_inserted },
              { label: "Duplicates Skipped", value: result.duplicates_skipped },
              { label: "P-H Rows After", value: result.ph_rows_after },
            ].map(({ label, value }) => (
              <div key={label} style={{
                padding: "0.65rem 0.85rem",
                background: "var(--bg-card)",
                borderRadius: "8px",
                border: "1px solid var(--border)",
              }}>
                <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginBottom: "0.15rem" }}>{label}</div>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--accent)" }}>{value ?? "—"}</div>
              </div>
            ))}
          </div>
          {result.products_synced?.length > 0 && (
            <div style={{ marginTop: "0.85rem" }}>
              <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.35rem" }}>Products synced:</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                {result.products_synced.map(p => (
                  <span key={p} style={{
                    padding: "0.2rem 0.55rem",
                    background: "rgba(99,102,241,0.12)",
                    color: "var(--accent)",
                    borderRadius: "999px",
                    fontSize: "0.7rem",
                    fontWeight: 600,
                    fontFamily: "monospace",
                  }}>{p}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
