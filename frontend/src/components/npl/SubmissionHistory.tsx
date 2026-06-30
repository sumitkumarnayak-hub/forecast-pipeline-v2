"use client";

import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

export default function SubmissionHistory() {
  const { readOnly, canApprove, hydrated } = useAuth();
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<{ types: string[]; statuses: string[]; product_ids: string[] }>({
    types: [],
    statuses: [],
    product_ids: [],
  });
  const [selTypes, setSelTypes] = useState<string[]>([]);
  const [selStatuses, setSelStatuses] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (selTypes.length) params.types = selTypes.join(",");
      if (selStatuses.length) params.statuses = selStatuses.join(",");
      const { data } = await api.get("/api/new-product-launch/submissions/log", { params });
      setRows(data.rows || []);
      setColumns(data.columns || []);
      setFilters(data.filters || { types: [], statuses: [], product_ids: [] });
      if (!selectedId && data.rows?.length) {
        const first = data.rows[0]["Submission_ID"];
        if (first) setSelectedId(String(first));
      }
    } catch {
      setRows([]);
    }
    setLoading(false);
  }, [selTypes, selStatuses, selectedId]);

  useEffect(() => {
    load();
  }, [load]);

  const patchStatus = async (status: string, reason = "") => {
    if (!selectedId) return;
    try {
      await api.patch(`/api/new-product-launch/submissions/${selectedId}/status`, { status, reason });
      setMsg(`${selectedId} → ${status}`);
      load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg(err?.response?.data?.detail || "Action failed");
    }
  };

  return (
    <div className="card" style={{ padding: "1.25rem" }}>
      <h4 style={{ margin: "0 0 1rem" }}>Submission History</h4>
      {msg && <div className="alert alert-info text-sm mb-3">{msg}</div>}

      <div className="grid-3 mb-3" style={{ maxWidth: 720 }}>
        <div className="form-group">
          <label className="form-label text-xs">Type</label>
          <select
            className="form-input text-sm"
            multiple
            style={{ minHeight: 72 }}
            value={selTypes}
            onChange={e => setSelTypes(Array.from(e.target.selectedOptions).map(o => o.value))}
          >
            {filters.types.map(t => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label text-xs">Status</label>
          <select
            className="form-input text-sm"
            multiple
            style={{ minHeight: 72 }}
            value={selStatuses}
            onChange={e => setSelStatuses(Array.from(e.target.selectedOptions).map(o => o.value))}
          >
            {filters.statuses.map(s => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label text-xs">Submission ID</label>
          <select className="form-input text-sm" value={selectedId} onChange={e => setSelectedId(e.target.value)}>
            {[...new Set(rows.map(r => String(r["Submission_ID"] ?? "")))].filter(Boolean).map(id => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <span className="spinner" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">No submissions in log.</p>
      ) : (
        <div className="table-wrap mb-4" style={{ maxHeight: 400, overflow: "auto" }}>
          <table>
            <thead>
              <tr>
                {columns.map(c => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {columns.map(c => (
                    <td key={c} style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>
                      {String(row[c] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hydrated && !readOnly && selectedId && (
        <div className="flex flex-wrap gap-2 items-end">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => patchStatus("Withdrawn")}>
            Withdraw
          </button>
          {canApprove && (
            <>
              <button type="button" className="btn btn-success btn-sm" onClick={() => patchStatus("Approved")}>
                Approve
              </button>
              <input
                className="form-input text-sm"
                placeholder="Rejection reason"
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
                style={{ maxWidth: 200 }}
              />
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() => patchStatus("Rejected", rejectReason)}
                disabled={!rejectReason.trim()}
              >
                Reject
              </button>
              <button type="button" className="btn btn-danger btn-sm" onClick={() => patchStatus("Voided")}>
                Void
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
