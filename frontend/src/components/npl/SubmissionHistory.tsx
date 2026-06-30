"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileText,
  History,
  RefreshCw,
  Search,
  XCircle,
} from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import FilterChipSelect from "@/components/ui/FilterChipSelect";

const DEFAULT_TYPES = ["New Launch", "Expansion", "Replacement"];
const DEFAULT_STATUSES = ["Pending", "Approved", "Rejected", "Withdrawn", "Voided", "Expired"];

const COL_LABELS: Record<string, string> = {
  Submission_ID: "Submission ID",
  Submission_Type: "Type",
  "Product ID": "Product ID",
  "Product Name": "Product",
  City: "City",
  Hub: "Hub",
  "Start Date": "Launch Date",
  Status: "Status",
  SLA: "SLA",
  Rejection_Reason: "Rejection Reason",
  Submitted_By: "Submitted By",
  Timestamp: "Submitted At",
};

const VISIBLE_COLUMNS = [
  "Submission_ID",
  "Submission_Type",
  "Product Name",
  "City",
  "Start Date",
  "Status",
  "SLA",
  "Submitted_By",
  "Timestamp",
];

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
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<{ types: string[]; statuses: string[]; product_ids: string[] }>({
    types: [],
    statuses: [],
    product_ids: [],
  });
  const [selTypes, setSelTypes] = useState<string[]>([]);
  const [selStatuses, setSelStatuses] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const typeOptions = useMemo(
    () => (filters.types.length ? filters.types : DEFAULT_TYPES),
    [filters.types],
  );
  const statusOptions = useMemo(
    () => (filters.statuses.length ? filters.statuses.filter(Boolean) : DEFAULT_STATUSES),
    [filters.statuses],
  );

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {};
      if (selTypes.length) params.types = selTypes.join(",");
      if (selStatuses.length) params.statuses = selStatuses.join(",");
      const { data } = await api.get("/api/new-product-launch/submissions/log", { params });
      setRows(data.rows || []);
      setColumns(data.columns || []);
      setFilters(data.filters || { types: [], statuses: [], product_ids: [] });
      setSelectedId(prev => {
        if (prev && (data.rows || []).some((r: Record<string, unknown>) => String(r["Submission_ID"]) === prev)) {
          return prev;
        }
        const first = data.rows?.[0]?.["Submission_ID"];
        return first ? String(first) : "";
      });
    } catch {
      setRows([]);
      setError("Could not load submission history.");
    }
    setLoading(false);
    setRefreshing(false);
  }, [selTypes, selStatuses]);

  useEffect(() => {
    load();
  }, [load]);

  const patchStatus = async (status: string, reason = "") => {
    if (!selectedId) return;
    try {
      await api.patch(`/api/new-product-launch/submissions/${selectedId}/status`, { status, reason });
      setMsg(`Submission ${selectedId} updated to ${status}.`);
      setRejectReason("");
      load(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg(err?.response?.data?.detail || "Action failed");
    }
  };

  const displayColumns = useMemo(() => {
    const preferred = VISIBLE_COLUMNS.filter(c => columns.includes(c));
    return preferred.length ? preferred : columns;
  }, [columns]);

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
          onClick={() => load(true)}
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
              {loading ? "Loading submissions…" : `${filteredRows.length.toLocaleString()} result${filteredRows.length === 1 ? "" : "s"}`}
            </span>
          </div>
          {search.trim() && filteredRows.length !== rows.length && (
            <span className="text-xs text-muted">
              Filtered from {rows.length.toLocaleString()} total
            </span>
          )}
        </div>

        {loading ? (
          <div className="npl-history-loading">
            <span className="spinner" />
            <p className="text-sm text-muted">Loading submission log…</p>
          </div>
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
                  {displayColumns.map(c => (
                    <th key={c}>{COL_LABELS[c] ?? c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row, i) => {
                  const id = String(row["Submission_ID"] ?? "");
                  const rowKey = id
                    ? `${id}-${String(row["Hub"] ?? "")}-${String(row["City"] ?? "")}-${i}`
                    : `row-${i}`;
                  const isSelected = Boolean(id) && selectedId === id;
                  return (
                    <tr
                      key={rowKey}
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
                      {displayColumns.map(c => (
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
              <span className="npl-history-detail-label">City</span>
              <span>{String(selectedRow["City"] ?? "—")}</span>
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

          <div className="npl-history-actions-buttons">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => patchStatus("Withdrawn")}>
              Withdraw
            </button>
            {canApprove && (
              <>
                <button type="button" className="btn btn-success btn-sm" onClick={() => patchStatus("Approved")}>
                  <CheckCircle2 size={14} />
                  Approve
                </button>
                <div className="npl-history-reject-wrap">
                  <input
                    className="form-input text-sm"
                    placeholder="Rejection reason (required to reject)"
                    value={rejectReason}
                    onChange={e => setRejectReason(e.target.value)}
                  />
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => patchStatus("Rejected", rejectReason)}
                    disabled={!rejectReason.trim()}
                  >
                    Reject
                  </button>
                </div>
                <button type="button" className="btn btn-danger btn-sm btn-outline" onClick={() => patchStatus("Voided")}>
                  Void
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
