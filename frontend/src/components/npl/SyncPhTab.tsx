"use client";

import { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { RefreshCw } from "lucide-react";

export default function SyncPhTab() {
  const { readOnly } = useAuth();
  const [pids, setPids] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
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
    try {
      const { data } = await api.post("/api/new-product-launch/sync-ph/preview", { product_ids });
      setPreview(data);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Preview failed", type: "danger" });
    } finally {
      setLoading(false);
    }
  };

  const confirmSync = async () => {
    if (!preview?.rows_to_add) return;
    setConfirming(true);
    try {
      const { data } = await api.post("/api/new-product-launch/sync-ph/confirm", {
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

  const rows = (preview?.rows_to_add as Record<string, unknown>[]) || [];
  const headers = (preview?.ph_headers as string[]) || [];

  return (
    <div className="card">
      <p className="text-sm text-muted mb-3">
        Preview and confirm P-H Master writes for new product IDs. Preview is a dry run — no sheet writes until you confirm.
      </p>
      {msg.text && <div className={`alert alert-${msg.type} mb-3 text-sm`}>{msg.text}</div>}
      <textarea
        className="form-input mb-3"
        rows={3}
        placeholder="Product IDs (comma or newline separated)…"
        value={pids}
        onChange={e => setPids(e.target.value)}
        disabled={readOnly}
      />
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button type="button" className="btn btn-secondary btn-sm" onClick={runPreview} disabled={loading || readOnly}>
          {loading ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <RefreshCw size={13} />}
          Preview sync
        </button>
        {rows.length > 0 && (
          <button type="button" className="btn btn-primary btn-sm" onClick={confirmSync} disabled={confirming || readOnly}>
            {confirming ? "Writing…" : `Confirm ${rows.length} rows`}
          </button>
        )}
      </div>
      {rows.length > 0 && headers.length > 0 && (
        <div className="table-wrap mt-4" style={{ maxHeight: 360, overflow: "auto" }}>
          <table>
            <thead>
              <tr>
                {headers.slice(0, 12).map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 50).map((row, i) => (
                <tr key={i}>
                  {headers.slice(0, 12).map(h => (
                    <td key={h} style={{ fontSize: "0.72rem" }}>
                      {String(row[h] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
