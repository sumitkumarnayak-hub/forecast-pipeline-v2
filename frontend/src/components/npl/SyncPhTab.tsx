"use client";

import { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { RefreshCw, Info, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";

interface PhSyncPreview {
  product_ids: string[];
  schema_errors: string[];
  not_in_p_master: string[];
  validation_errors: string[];
  already_exists: string[];
  rows_to_add: Record<string, unknown>[];
  ph_headers: string[];
  active_hub_count: number;
}

export default function SyncPhTab() {
  const { canWrite } = useAuth();
  const [pids, setPids] = useState("");
  const [preview, setPreview] = useState<PhSyncPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });

  const runPreview = async () => {
    const product_ids = pids.split(/[,\s]+/).map(s => s.trim()).filter(Boolean);
    if (!product_ids.length) {
      setMsg({ text: "Enter at least one product ID", type: "warning" });
      return;
    }
    setLoading(true);
    setMsg({ text: "", type: "" });
    setPreview(null);
    try {
      const { data } = await api.post<PhSyncPreview>("/api/new-product-launch/sync-ph/preview", { product_ids });
      setPreview(data);
      if (data.rows_to_add.length === 0) {
        setMsg({
          text: data.already_exists.length > 0
            ? `All ${data.already_exists.length} product(s) already exist in P-H Master.`
            : "No rows to add — check for validation errors below.",
          type: "warning",
        });
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Preview failed", type: "danger" });
    } finally {
      setLoading(false);
    }
  };

  const confirmSync = async () => {
    if (!preview?.rows_to_add?.length) return;
    setConfirming(true);
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post<{ detail: string }>("/api/new-product-launch/sync-ph/confirm", {
        product_ids: preview.product_ids,
        ph_headers: preview.ph_headers,
        rows_to_add: preview.rows_to_add,
      });
      setMsg({ text: data.detail, type: "success" });
      setPreview(null);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Confirm failed", type: "danger" });
    } finally {
      setConfirming(false);
    }
  };

  const rows = preview?.rows_to_add ?? [];
  const headers = preview?.ph_headers ?? [];

  return (
    <div style={{ maxWidth: 720 }}>
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
          <strong style={{ color: "var(--text-primary)" }}>P-H Master Sync</strong> — Preview hub-level rows for new
          product IDs and confirm to write them to the P-H Master sheet.
          Preview is a <strong>dry run</strong> — no sheet writes until you confirm.
        </div>
      </div>

      {/* Alert */}
      {msg.text && (
        <div className={`alert alert-${msg.type} mb-4`} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {msg.type === "success" ? <CheckCircle2 size={15} />
            : msg.type === "warning" ? <AlertTriangle size={15} />
            : <XCircle size={15} />}
          {msg.text}
        </div>
      )}

      {/* Input */}
      <label className="text-sm" style={{ display: "block", fontWeight: 600, marginBottom: "0.4rem", color: "var(--text-secondary)" }}>
        Product IDs
      </label>
      <textarea
        className="form-input mb-1"
        rows={3}
        placeholder="Product IDs (comma or newline separated)…"
        value={pids}
        onChange={e => setPids(e.target.value)}
        disabled={!canWrite}
        style={{ resize: "vertical", fontFamily: "monospace", fontSize: "0.8rem" }}
      />
      <p className="text-xs text-muted mb-4">e.g. P001, P002, P003</p>

      {/* Actions */}
      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "1.25rem" }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={runPreview}
          disabled={loading || !canWrite}
          style={{ minWidth: 140 }}
        >
          {loading ? (
            <><span className="spinner" style={{ width: 13, height: 13 }} /> Previewing…</>
          ) : (
            <><RefreshCw size={13} /> Preview Sync</>
          )}
        </button>

        {rows.length > 0 && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={confirmSync}
            disabled={confirming || !canWrite}
            style={{ minWidth: 160 }}
          >
            {confirming ? (
              <><span className="spinner" style={{ width: 13, height: 13 }} /> Writing to sheet…</>
            ) : (
              <><CheckCircle2 size={14} /> Confirm — Write {rows.length} row{rows.length !== 1 ? "s" : ""}</>
            )}
          </button>
        )}
      </div>

      {/* Validation warnings */}
      {preview && (preview.schema_errors.length > 0 || preview.not_in_p_master.length > 0 || preview.validation_errors.length > 0) && (
        <div style={{
          padding: "0.85rem 1rem",
          background: "rgba(245,158,11,0.07)",
          border: "1px solid rgba(245,158,11,0.3)",
          borderRadius: "8px",
          marginBottom: "1rem",
        }}>
          <div style={{ fontWeight: 700, fontSize: "0.78rem", color: "#f59e0b", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <AlertTriangle size={13} /> Validation Issues
          </div>
          {preview.schema_errors.map((e, i) => <div key={i} className="text-xs text-muted" style={{ marginBottom: "0.2rem" }}>• {e}</div>)}
          {preview.not_in_p_master.length > 0 && (
            <div className="text-xs text-muted">• Not in P Master: {preview.not_in_p_master.join(", ")}</div>
          )}
          {preview.validation_errors.map((e, i) => <div key={i} className="text-xs text-muted" style={{ marginBottom: "0.2rem" }}>• {e}</div>)}
          {preview.already_exists.length > 0 && (
            <div className="text-xs text-muted">• Already in P-H Master: {preview.already_exists.join(", ")}</div>
          )}
        </div>
      )}

      {/* Summary stats */}
      {preview && (
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: rows.length > 0 ? "1rem" : 0 }}>
          {[
            { label: "Rows to Add", value: rows.length, accent: true },
            { label: "Active Hubs", value: preview.active_hub_count },
            { label: "Already Exists", value: preview.already_exists.length },
            { label: "Not in P Master", value: preview.not_in_p_master.length },
          ].map(({ label, value, accent }) => (
            <div key={label} style={{
              padding: "0.55rem 0.85rem",
              background: "var(--bg-elevated)",
              border: `1px solid ${accent && value > 0 ? "var(--accent)" : "var(--border)"}`,
              borderRadius: "8px",
              minWidth: 100,
            }}>
              <div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{label}</div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: accent && value > 0 ? "var(--accent)" : "var(--text-primary)" }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Preview table */}
      {rows.length > 0 && headers.length > 0 && (
        <div style={{
          border: "1px solid var(--border)",
          borderRadius: "8px",
          overflow: "hidden",
          marginTop: "0.5rem",
        }}>
          <div style={{
            padding: "0.5rem 1rem",
            background: "var(--bg-elevated)",
            fontSize: "0.72rem",
            color: "var(--text-muted)",
            borderBottom: "1px solid var(--border)",
          }}>
            Showing first 12 columns · {rows.length} row{rows.length !== 1 ? "s" : ""} to add
          </div>
          <div style={{ maxHeight: 340, overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "var(--bg-elevated)" }}>
                  {headers.slice(0, 12).map(h => (
                    <th key={h} style={{
                      padding: "0.45rem 0.75rem",
                      fontSize: "0.68rem",
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      textAlign: "left",
                      whiteSpace: "nowrap",
                      borderBottom: "1px solid var(--border)",
                      position: "sticky",
                      top: 0,
                      background: "var(--bg-elevated)",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 50).map((row, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    {headers.slice(0, 12).map(h => (
                      <td key={h} style={{
                        padding: "0.4rem 0.75rem",
                        fontSize: "0.7rem",
                        color: "var(--text-secondary)",
                        whiteSpace: "nowrap",
                        maxWidth: 150,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}>
                        {String(row[h] ?? "—")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
