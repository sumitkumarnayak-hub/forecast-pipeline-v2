"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  FileText,
  History,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  XCircle,
} from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useStaleFetch } from "@/hooks/useStaleFetch";
import FilterChipSelect from "@/components/ui/FilterChipSelect";
import TableSkeleton from "@/components/ui/TableSkeleton";
import StatGridSkeleton from "@/components/ui/StatGridSkeleton";
import { cacheInvalidate } from "@/lib/queryCache";

const DEFAULT_TYPES = ["New Launch", "Expansion", "Replacement"];
const DEFAULT_STATUSES = ["Pending", "Approved", "Rejected", "Withdrawn", "Voided", "Expired"];

type LogPayload = {
  rows: Record<string, unknown>[];
  columns: string[];
  filters: { types: string[]; statuses: string[]; product_ids: string[] };
  view?: string;
};

type ApprovalAppendResult = {
  rows_appended?: number;
  rows_skipped?: number;
  matched_rows?: number;
  worksheet?: string;
};

type StatusPatchResponse = {
  detail?: string;
  append?: ApprovalAppendResult | null;
};

type ActionStep = {
  id: string;
  label: string;
  state: "pending" | "active" | "done" | "failed";
};

type SheetRow = Record<string, string | number> & { _sheet_row_index: number };
const COL_LABELS: Record<string, string> = {
  Submission_ID: "Submission ID",
  Submission_Type: "Type",
  "Product ID": "Product ID",
  "Product Name": "Product",
  City: "City",
  Hub: "Hub",
  Hub_Count: "Hubs",
  City_Count: "Cities",
  Cities: "City list",
  "Start Date": "Launch Date",
  Status: "Status",
  SLA: "SLA",
  Rejection_Reason: "Rejection Reason",
  Submitted_By: "Submitted By",
  Timestamp: "Submitted At",
};

function fmtDate(value: unknown): string {
  if (!value) return "—";
  const d = new Date(String(value));
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function fmtDateShort(value: unknown): string {
  if (!value) return "—";
  const d = new Date(String(value));
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase();
  if (s === "approved") return "badge-green";
  if (s === "pending") return "badge-yellow";
  if (s === "rejected" || s === "voided" || s === "expired") return "badge-red";
  if (s === "withdrawn") return "badge-gray";
  return "badge-gray";
}

function typeBadgeClass(type: string): string {
  if (type === "New Launch") return "badge-blue";
  if (type === "Expansion") return "badge-green";
  if (type === "Replacement") return "badge-yellow";
  return "badge-gray";
}

function renderCell(col: string, value: unknown) {
  const text = value == null || value === "" ? "—" : String(value);

  if (col === "Status") {
    return <span className={`badge ${statusBadgeClass(text)}`}>{text}</span>;
  }
  if (col === "Submission_Type") {
    return <span className={`badge ${typeBadgeClass(text)}`}>{text}</span>;
  }
  if (col === "SLA") {
    if (!text || text === "—") return <span className="text-muted">—</span>;
    const urgent = text === "OVERDUE" || text === "EXPIRED";
    return (
      <span className={`badge ${urgent ? "badge-red" : "badge-gray"}`}>
        {urgent && <AlertTriangle size={10} />}
        {text}
      </span>
    );
  }
  if (col === "Timestamp") return fmtDate(value);
  if (col === "Start Date") return fmtDateShort(value);
  if (col === "Submission_ID") {
    return (
      <span className="npl-history-id" title={text}>
        {text}
      </span>
    );
  }
  if (col === "Product Name") {
    return <span className="npl-history-product">{text}</span>;
  }
  if (col === "Cities") {
    return (
      <span className="npl-history-cities" title={text}>
        {text}
      </span>
    );
  }
  if (col === "Rejection_Reason" && text !== "—") {
    return (
      <span className="npl-history-reason" title={text}>
        {text}
      </span>
    );
  }
  return text;
}

export default function SubmissionHistory() {
  const { readOnly, canApprove, hydrated } = useAuth();
  const [selTypes, setSelTypes] = useState<string[]>([]);
  const [selStatuses, setSelStatuses] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [msg, setMsg] = useState("");
  const [actionSteps, setActionSteps] = useState<ActionStep[]>([]);
  const [actingStatus, setActingStatus] = useState("");
  const [hubRows, setHubRows] = useState<Record<string, unknown>[]>([]);
  const [hubLoading, setHubLoading] = useState(false);

  // Actions dropdown
  const [actionsOpen, setActionsOpen] = useState(false);
  const actionsRef = useRef<HTMLDivElement>(null);

  // Delete-rows modal
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [sheetRows, setSheetRows] = useState<SheetRow[]>([]);
  const [sheetRowsLoading, setSheetRowsLoading] = useState(false);
  const [checkedIndices, setCheckedIndices] = useState<Set<number>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [deleteMsg, setDeleteMsg] = useState({ text: "", type: "" });

  const logCacheKey = useMemo(
    () => `npl:submission-log:summary:${selTypes.join(",")}|${selStatuses.join(",")}`,
    [selTypes, selStatuses],
  );

  const fetchLog = useCallback(async (): Promise<LogPayload> => {
    const params: Record<string, string> = { view: "summary" };
    if (selTypes.length) params.types = selTypes.join(",");
    if (selStatuses.length) params.statuses = selStatuses.join(",");
    const { data } = await api.get<LogPayload>("/api/new-product-launch/submissions/log", { params });
    return data;
  }, [selTypes, selStatuses]);

  const { data, loading, refreshing, error, reload } = useStaleFetch<LogPayload>({
    cacheKey: logCacheKey,
    fetcher: fetchLog,
    deps: [logCacheKey],
  });

  const rows = data?.rows ?? [];
  const columns = data?.columns ?? [];
  const filters = data?.filters ?? { types: [], statuses: [], product_ids: [] };

  useEffect(() => {
    if (!rows.length) {
      setSelectedId("");
      return;
    }
    setSelectedId(prev =>
      prev && rows.some(r => String(r["Submission_ID"]) === prev)
        ? prev
        : String(rows[0]["Submission_ID"] ?? ""),
    );
  }, [rows]);

  useEffect(() => {
    if (!selectedId) {
      setHubRows([]);
      return;
    }
    let cancelled = false;
    setHubLoading(true);
    api
      .get<LogPayload>("/api/new-product-launch/submissions/log", {
        params: { view: "detail", submission_id: selectedId },
      })
      .then(({ data: detail }) => {
        if (!cancelled) setHubRows(detail.rows || []);
      })
      .catch(() => {
        if (!cancelled) setHubRows([]);
      })
      .finally(() => {
        if (!cancelled) setHubLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const typeOptions = useMemo(
    () => (filters.types.length ? filters.types : DEFAULT_TYPES),
    [filters.types],
  );
  const statusOptions = useMemo(
    () => (filters.statuses.length ? filters.statuses.filter(Boolean) : DEFAULT_STATUSES),
    [filters.statuses],
  );

  const patchStatus = async (status: string, reason = "") => {
    if (!selectedId || actingStatus) return;
    const isApproval = status === "Approved";
    setActingStatus(status);
    setMsg("");
    if (isApproval) {
      setActionSteps([
        { id: "status", label: "Approve submission", state: "done" },
        { id: "append", label: "Append to New Product Launch Google Sheet", state: "active" },
        { id: "refresh", label: "Refresh submission history", state: "pending" },
      ]);
    }

    try {
      const { data: result } = await api.patch<StatusPatchResponse>(
        `/api/new-product-launch/submissions/${selectedId}/status`,
        { status, reason },
      );
      if (isApproval) {
        setActionSteps([
          { id: "status", label: "Approve submission", state: "done" },
          { id: "append", label: "Append to New Product Launch Google Sheet", state: "done" },
          { id: "refresh", label: "Refresh submission history", state: "active" },
        ]);
      }
      setRejectReason("");
      cacheInvalidate(logCacheKey);
      await reload(true);

      if (isApproval) {
        const append = result.append;
        setActionSteps([
          { id: "status", label: "Approve submission", state: "done" },
          { id: "append", label: "Append to New Product Launch Google Sheet", state: "done" },
          { id: "refresh", label: "Refresh submission history", state: "done" },
        ]);
        const appended = append?.rows_appended ?? 0;
        const skipped = append?.rows_skipped ?? 0;
        setMsg(`Submission ${selectedId} approved. Appended ${appended} row${appended === 1 ? "" : "s"} to ${append?.worksheet || "City_Plan"}${skipped ? `, skipped ${skipped} existing` : ""}.`);
      } else {
        setMsg(`Submission ${selectedId} updated to ${status}.`);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      if (isApproval) {
        setActionSteps(prev => prev.map(step => (step.state === "active" ? { ...step, state: "failed" } : step)));
      }
      setMsg(err?.response?.data?.detail || "Action failed");
    } finally {
      setActingStatus("");
      if (isApproval) {
        window.setTimeout(() => setActionSteps([]), 3000);
      }
    }
  };

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(row =>
      Object.values(row).some(v => String(v ?? "").toLowerCase().includes(q)),
    );
  }, [rows, search]);

  const stats = useMemo(() => {
    const pending = rows.filter(r => String(r["Status"] ?? "").toLowerCase() === "pending").length;
    const approved = rows.filter(r => String(r["Status"] ?? "").toLowerCase() === "approved").length;
    const slaAlerts = rows.filter(r => {
      const sla = String(r["SLA"] ?? "");
      return sla === "OVERDUE" || sla === "EXPIRED";
    }).length;
    return { total: rows.length, pending, approved, slaAlerts };
  }, [rows]);

  const selectedRow = useMemo(
    () => rows.find(r => String(r["Submission_ID"] ?? "") === selectedId) ?? null,
    [rows, selectedId],
  );

  const hasActiveFilters = selTypes.length > 0 || selStatuses.length > 0 || search.trim().length > 0;

  const clearFilters = () => {
    setSelTypes([]);
    setSelStatuses([]);
    setSearch("");
  };

  const showInitialSkeleton = loading && !data;

  return (
    <div className="npl-history">
      <div className="npl-history-header">
        <div className="npl-history-header-text">
          <div className="npl-history-title-row">
            <span className="npl-history-icon">
              <History size={18} />
            </span>
            <div>
              <h4 className="npl-history-title">Submission History</h4>
              <p className="npl-history-subtitle">
                Track launch submissions, filter by type or status, and approve or reject pending requests.
              </p>
            </div>
          </div>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm npl-history-refresh"
          onClick={() => reload(true)}
          disabled={loading || refreshing}
        >
          <RefreshCw size={14} className={refreshing ? "npl-history-spin" : ""} />
          Refresh
        </button>
      </div>

      {msg && (
        <div className="alert alert-info text-sm mb-3 npl-history-alert">
          <CheckCircle2 size={15} />
          {msg}
        </div>
      )}
      {error && (
        <div className="alert alert-danger text-sm mb-3 npl-history-alert">
          <XCircle size={15} />
          {error}
        </div>
      )}

      {actionSteps.length > 0 && (
        <div className="alert alert-info text-sm mb-3 npl-history-alert">
          <div className="npl-history-action-steps">
            {actionSteps.map(step => (
              <span key={step.id} className={`npl-history-action-step npl-history-action-step-${step.state}`}>
                {step.state === "active" ? <Loader2 size={14} className="npl-history-spin" /> : <CheckCircle2 size={14} />}
                {step.label}
              </span>
            ))}
          </div>
        </div>
      )}
      {showInitialSkeleton ? (
        <StatGridSkeleton />
      ) : (
        <div className="stat-grid npl-history-stats">
          <div className="stat-card npl-history-stat">
            <div className="stat-label">Showing</div>
            <div className="stat-value">{stats.total.toLocaleString()}</div>
            <div className="npl-history-stat-hint">submissions</div>
          </div>
          <div className="stat-card npl-history-stat npl-history-stat-pending">
            <div className="stat-label">Pending</div>
            <div className="stat-value">{stats.pending.toLocaleString()}</div>
            <div className="npl-history-stat-hint">awaiting review</div>
          </div>
          <div className="stat-card npl-history-stat npl-history-stat-approved">
            <div className="stat-label">Approved</div>
            <div className="stat-value">{stats.approved.toLocaleString()}</div>
            <div className="npl-history-stat-hint">in current view</div>
          </div>
          <div className="stat-card npl-history-stat npl-history-stat-sla">
            <div className="stat-label">SLA alerts</div>
            <div className="stat-value">{stats.slaAlerts.toLocaleString()}</div>
            <div className="npl-history-stat-hint">overdue / expired</div>
          </div>
        </div>
      )}

      <div className="npl-history-toolbar card">
        <div className="npl-history-filters">
          <FilterChipSelect
            label="Submission type"
            options={typeOptions}
            selected={selTypes}
            onChange={setSelTypes}
            placeholder="Filter by type…"
            maxHeight={140}
          />
          <FilterChipSelect
            label="Status"
            options={statusOptions}
            selected={selStatuses}
            onChange={setSelStatuses}
            placeholder="Filter by status…"
            maxHeight={160}
          />
        </div>
        <div className="npl-history-search-wrap">
          <label className="filter-chip-label" htmlFor="npl-history-search">
            Search
          </label>
          <div className="npl-history-search">
            <Search size={15} className="npl-history-search-icon" />
            <input
              id="npl-history-search"
              className="form-input text-sm"
              placeholder="Search product, city, ID, submitter…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          {hasActiveFilters && (
            <button type="button" className="filter-chip-clear npl-history-clear" onClick={clearFilters}>
              Clear all filters
            </button>
          )}
        </div>
      </div>

      <div className="npl-history-table-card card">
        <div className="npl-history-table-head">
          <div className="npl-history-table-title">
            <FileText size={16} />
            <span>
              {showInitialSkeleton
                ? "Loading submissions…"
                : `${filteredRows.length.toLocaleString()} submission${filteredRows.length === 1 ? "" : "s"}`}
            </span>
          </div>
          {search.trim() && filteredRows.length !== rows.length && (
            <span className="text-xs text-muted">
              Filtered from {rows.length.toLocaleString()} total
            </span>
          )}
        </div>

        {showInitialSkeleton ? (
          <TableSkeleton rows={8} cols={6} />
        ) : filteredRows.length === 0 ? (
          <div className="npl-history-empty">
            <History size={32} strokeWidth={1.25} />
            <p className="npl-history-empty-title">No submissions found</p>
            <p className="text-sm text-muted">
              {hasActiveFilters
                ? "Try adjusting your filters or search terms."
                : "Submissions will appear here once launch plans are submitted."}
            </p>
            {hasActiveFilters && (
              <button type="button" className="btn btn-secondary btn-sm mt-2" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <div className="table-wrap npl-history-table-wrap">
            <table className="npl-history-table">
              <thead>
                <tr>
                  {columns.map(c => (
                    <th key={c}>{COL_LABELS[c] ?? c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map(row => {
                  const id = String(row["Submission_ID"] ?? "");
                  const isSelected = Boolean(id) && selectedId === id;
                  return (
                    <tr
                      key={id}
                      className={isSelected ? "npl-history-row-selected" : ""}
                      onClick={() => setSelectedId(id)}
                      tabIndex={0}
                      onKeyDown={e => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedId(id);
                        }
                      }}
                    >
                      {columns.map(c => (
                        <td key={c}>{renderCell(c, row[c])}</td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {hydrated && !readOnly && selectedRow && (
        <div className="npl-history-actions card">
          <div className="npl-history-actions-head">
            <div>
              <p className="npl-history-actions-label">Selected submission</p>
              <p className="npl-history-actions-id">{selectedId}</p>
            </div>
            <div className="npl-history-actions-meta">
              <span className={`badge ${typeBadgeClass(String(selectedRow["Submission_Type"] ?? ""))}`}>
                {String(selectedRow["Submission_Type"] ?? "—")}
              </span>
              <span className={`badge ${statusBadgeClass(String(selectedRow["Status"] ?? ""))}`}>
                {String(selectedRow["Status"] ?? "—")}
              </span>
              {selectedRow["SLA"] ? (
                <span className="badge badge-red">
                  <Clock3 size={10} />
                  {String(selectedRow["SLA"])}
                </span>
              ) : null}
            </div>
          </div>

          <div className="npl-history-actions-details">
            <div>
              <span className="npl-history-detail-label">Product</span>
              <span>{String(selectedRow["Product Name"] ?? "—")}</span>
            </div>
            <div>
              <span className="npl-history-detail-label">Cities</span>
              <span>{String(selectedRow["Cities"] ?? "—")}</span>
            </div>
            <div>
              <span className="npl-history-detail-label">Hub rows</span>
              <span>{String(selectedRow["Hub_Count"] ?? hubRows.length)}</span>
            </div>
            <div>
              <span className="npl-history-detail-label">Launch date</span>
              <span>{fmtDateShort(selectedRow["Start Date"])}</span>
            </div>
            <div>
              <span className="npl-history-detail-label">Submitted by</span>
              <span>{String(selectedRow["Submitted_By"] ?? "—")}</span>
            </div>
          </div>

          {(hubLoading || hubRows.length > 0) && (
            <div className="npl-history-hub-detail mb-3">
              <p className="text-xs font-semibold mb-2">Hub breakdown</p>
              {hubLoading ? (
                <TableSkeleton rows={3} cols={4} />
              ) : (
                <div className="table-wrap" style={{ maxHeight: 200 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>City</th>
                        <th>Hub</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {hubRows.map((hr, i) => (
                        <tr key={`${hr["City"]}-${hr["Hub"]}-${i}`}>
                          <td>{String(hr["City"] ?? "—")}</td>
                          <td>{String(hr["Hub"] ?? "—")}</td>
                          <td>{String(hr["Status"] ?? "—")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── Actions dropdown ─────────────────────────────────── */}
          <div className="npl-history-actions-buttons" style={{ position: "relative" }} ref={actionsRef}>

            {/* Close dropdown on outside click */}
            {actionsOpen && (
              <div
                style={{ position: "fixed", inset: 0, zIndex: 40 }}
                onClick={() => setActionsOpen(false)}
              />
            )}

            <button
              type="button"
              className="btn btn-primary btn-sm"
              style={{ display: "flex", alignItems: "center", gap: 5, position: "relative", zIndex: 41 }}
              onClick={() => setActionsOpen(v => !v)}
              disabled={!!actingStatus}
            >
              Actions
              {actionsOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>

            {actionsOpen && (
              <div style={{
                position: "absolute", bottom: "calc(100% + 6px)", left: 0,
                background: "var(--bg-card)", border: "1px solid var(--border)",
                borderRadius: "10px", boxShadow: "0 8px 24px rgba(0,0,0,0.18)",
                minWidth: 220, zIndex: 42, overflow: "hidden",
                padding: "4px 0",
              }}>

                {/* Status-aware actions */}
                {(() => {
                  const status = String(selectedRow?.["Status"] ?? "").toLowerCase();

                  return (
                    <>
                      {/* Pending actions */}
                      {status === "pending" && canApprove && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ width: "100%", justifyContent: "flex-start", borderRadius: 0, gap: 8, padding: "0.55rem 1rem", color: "var(--color-success, #22c55e)" }}
                          onClick={() => { setActionsOpen(false); patchStatus("Approved"); }}
                          disabled={!!actingStatus}
                        >
                          <CheckCircle2 size={14} /> Approve
                        </button>
                      )}

                      {status === "pending" && canApprove && (
                        <>
                          <div style={{ padding: "2px 1rem" }}>
                            <input
                              className="form-input text-sm"
                              placeholder="Rejection reason (required)"
                              value={rejectReason}
                              onChange={e => setRejectReason(e.target.value)}
                              style={{ width: "100%", fontSize: "0.75rem" }}
                            />
                          </div>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            style={{ width: "100%", justifyContent: "flex-start", borderRadius: 0, gap: 8, padding: "0.55rem 1rem", color: "var(--danger, #ef4444)" }}
                            onClick={() => { setActionsOpen(false); patchStatus("Rejected", rejectReason); }}
                            disabled={!rejectReason.trim() || !!actingStatus}
                          >
                            <XCircle size={14} /> Reject
                          </button>
                        </>
                      )}

                      {status === "pending" && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ width: "100%", justifyContent: "flex-start", borderRadius: 0, gap: 8, padding: "0.55rem 1rem" }}
                          onClick={() => { setActionsOpen(false); patchStatus("Withdrawn"); }}
                          disabled={!!actingStatus}
                        >
                          Withdraw
                        </button>
                      )}

                      {/* Void for approved */}
                      {status === "approved" && canApprove && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ width: "100%", justifyContent: "flex-start", borderRadius: 0, gap: 8, padding: "0.55rem 1rem", color: "var(--danger, #ef4444)" }}
                          onClick={() => { setActionsOpen(false); patchStatus("Voided"); }}
                          disabled={!!actingStatus}
                        >
                          <XCircle size={14} /> Void
                        </button>
                      )}

                      {/* Delete rows for rejected */}
                      {(status === "rejected" || status === "voided") && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ width: "100%", justifyContent: "flex-start", borderRadius: 0, gap: 8, padding: "0.55rem 1rem", color: "var(--danger, #ef4444)" }}
                          onClick={async () => {
                            setActionsOpen(false);
                            setDeleteMsg({ text: "", type: "" });
                            setCheckedIndices(new Set());
                            setDeleteModalOpen(true);
                            setSheetRowsLoading(true);
                            try {
                              const { data } = await api.get<{ rows: SheetRow[] }>(`/api/new-product-launch/submissions/${selectedId}/rows`);
                              setSheetRows(data.rows || []);
                            } catch {
                              setSheetRows([]);
                            } finally {
                              setSheetRowsLoading(false);
                            }
                          }}
                        >
                          <Trash2 size={14} /> Delete rows from sheet
                        </button>
                      )}

                      {/* Fallback if no status-specific action */}
                      {!["pending", "approved", "rejected", "voided"].includes(status) && (
                        <div style={{ padding: "0.75rem 1rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          No actions available
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            )}
          </div>

          {/* ── Delete rows modal ─────────────────────────────────── */}
          {deleteModalOpen && (
            <div style={{
              position: "fixed", inset: 0, zIndex: 100,
              background: "rgba(0,0,0,0.55)", backdropFilter: "blur(3px)",
              display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
            }}>
              <div style={{
                background: "var(--bg-card)", border: "1px solid var(--border)",
                borderRadius: "16px", width: "100%", maxWidth: 640,
                boxShadow: "0 24px 60px rgba(0,0,0,0.35)",
                display: "flex", flexDirection: "column", maxHeight: "90vh",
              }}>
                {/* Header */}
                <div style={{ padding: "1.25rem 1.5rem", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 36, height: 36, borderRadius: "10px", background: "rgba(239,68,68,0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Trash2 size={16} style={{ color: "#ef4444" }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <p style={{ margin: 0, fontWeight: 700, fontSize: "0.9rem", color: "var(--text-primary)" }}>Delete rows from Submission_Log?</p>
                    <p style={{ margin: 0, fontSize: "0.72rem", color: "var(--text-muted)" }}>Submission: {selectedId} · Check the rows you want to delete</p>
                  </div>
                  <button type="button" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: "4px" }} onClick={() => setDeleteModalOpen(false)}>
                    <XCircle size={18} />
                  </button>
                </div>

                {/* Body */}
                <div style={{ overflowY: "auto", flex: 1, padding: "1rem 1.5rem" }}>
                  {deleteMsg.text && (
                    <div className={`alert alert-${deleteMsg.type} text-sm mb-3`} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {deleteMsg.type === "success" ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                      {deleteMsg.text}
                    </div>
                  )}

                  {sheetRowsLoading ? (
                    <TableSkeleton rows={4} cols={3} />
                  ) : sheetRows.length === 0 ? (
                    <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", textAlign: "center", padding: "1.5rem 0" }}>No rows found in the sheet for this submission.</p>
                  ) : (
                    <div className="table-wrap" style={{ borderRadius: 8, border: "1px solid var(--border)" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.77rem" }}>
                        <thead>
                          <tr style={{ background: "rgba(255,255,255,0.03)", borderBottom: "1px solid var(--border)" }}>
                            <th style={{ padding: "0.5rem 0.75rem", width: 36 }}>
                              <input
                                type="checkbox"
                                checked={sheetRows.length > 0 && checkedIndices.size === sheetRows.length}
                                onChange={e => {
                                  if (e.target.checked) {
                                    setCheckedIndices(new Set(sheetRows.map(r => r._sheet_row_index)));
                                  } else {
                                    setCheckedIndices(new Set());
                                  }
                                }}
                                title="Select all"
                              />
                            </th>
                            <th style={{ padding: "0.5rem 0.75rem", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", fontSize: "0.62rem", letterSpacing: "0.04em" }}>Row #</th>
                            <th style={{ padding: "0.5rem 0.75rem", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", fontSize: "0.62rem", letterSpacing: "0.04em" }}>City</th>
                            <th style={{ padding: "0.5rem 0.75rem", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", fontSize: "0.62rem", letterSpacing: "0.04em" }}>Hub</th>
                            <th style={{ padding: "0.5rem 0.75rem", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", fontSize: "0.62rem", letterSpacing: "0.04em" }}>Start Date</th>
                            <th style={{ padding: "0.5rem 0.75rem", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", fontSize: "0.62rem", letterSpacing: "0.04em" }}>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sheetRows.map((sr) => {
                            const idx = sr._sheet_row_index;
                            const checked = checkedIndices.has(idx);
                            return (
                              <tr
                                key={idx}
                                style={{
                                  borderBottom: "1px solid var(--border)",
                                  background: checked ? "rgba(239,68,68,0.06)" : undefined,
                                  cursor: "pointer",
                                  transition: "background 0.12s",
                                }}
                                onClick={() => {
                                  setCheckedIndices(prev => {
                                    const next = new Set(prev);
                                    if (next.has(idx)) next.delete(idx); else next.add(idx);
                                    return next;
                                  });
                                }}
                              >
                                <td style={{ padding: "0.45rem 0.75rem" }} onClick={e => e.stopPropagation()}>
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={() => {
                                      setCheckedIndices(prev => {
                                        const next = new Set(prev);
                                        if (next.has(idx)) next.delete(idx); else next.add(idx);
                                        return next;
                                      });
                                    }}
                                  />
                                </td>
                                <td style={{ padding: "0.45rem 0.75rem", color: "var(--text-muted)", fontFamily: "monospace", fontSize: "0.7rem" }}>{idx}</td>
                                <td style={{ padding: "0.45rem 0.75rem", fontWeight: 500 }}>{String(sr["City"] ?? sr["city_name"] ?? "—")}</td>
                                <td style={{ padding: "0.45rem 0.75rem" }}>{String(sr["Hub"] ?? sr["hub_name"] ?? "—")}</td>
                                <td style={{ padding: "0.45rem 0.75rem", color: "var(--text-secondary)" }}>{String(sr["Start Date"] ?? "")}</td>
                                <td style={{ padding: "0.45rem 0.75rem" }}>
                                  <span className={`badge ${statusBadgeClass(String(sr["Status"] ?? ""))}`} style={{ fontSize: "0.6rem" }}>{String(sr["Status"] ?? "—")}</span>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Footer */}
                <div style={{ padding: "1rem 1.5rem", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10, justifyContent: "space-between" }}>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {checkedIndices.size > 0 ? `${checkedIndices.size} row${checkedIndices.size !== 1 ? "s" : ""} selected` : "Select rows to delete"}
                  </span>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDeleteModalOpen(false)} disabled={deleting}>
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      style={{ display: "flex", alignItems: "center", gap: 6 }}
                      disabled={checkedIndices.size === 0 || deleting}
                      onClick={async () => {
                        setDeleting(true);
                        setDeleteMsg({ text: "", type: "" });
                        try {
                          const { data } = await api.delete<{ detail: string; deleted_count: number; submission_fully_deleted: boolean }>(
                            `/api/new-product-launch/submissions/${selectedId}/rows`,
                            { data: { row_indices: Array.from(checkedIndices) } },
                          );
                          setDeleteMsg({ text: data.detail || `Deleted ${data.deleted_count} row(s)`, type: "success" });
                          setCheckedIndices(new Set());
                          // Reload sheet rows to show remaining rows
                          const refresh = await api.get<{ rows: SheetRow[] }>(`/api/new-product-launch/submissions/${selectedId}/rows`);
                          setSheetRows(refresh.data.rows || []);
                          // Refresh submission list
                          cacheInvalidate(logCacheKey);
                          reload(true);
                        } catch (e: unknown) {
                          const err = e as { response?: { data?: { detail?: string } } };
                          setDeleteMsg({ text: err?.response?.data?.detail || "Delete failed", type: "danger" });
                        } finally {
                          setDeleting(false);
                        }
                      }}
                    >
                      {deleting ? <Loader2 size={13} className="npl-history-spin" /> : <Trash2 size={13} />}
                      {deleting ? "Deleting…" : `Delete ${checkedIndices.size > 0 ? checkedIndices.size : ""} row${checkedIndices.size !== 1 ? "s" : ""}`}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
