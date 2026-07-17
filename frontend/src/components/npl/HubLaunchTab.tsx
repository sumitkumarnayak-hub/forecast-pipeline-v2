"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  RefreshCw, CheckCircle2, XCircle, AlertTriangle,
  Landmark, Eye, Database, ArrowLeftRight, Bell,
  ChevronRight, Clock, ChevronDown, ChevronUp, Plus, X,
} from "lucide-react";

interface FFRow { [key: string]: string | number; }
interface FFInputData {
  rows: FFRow[]; headers: string[]; row_count: number;
  content_hash: string; cache_last_updated: string | null; _elapsed_ms?: number;
}
interface DiffEntry {
  key: string; before: Record<string, string>; after: Record<string, string>;
  row: FFRow; changed_cells: string[];
}
interface VersionDiff {
  added: FFRow[]; removed: FFRow[]; modified: DiffEntry[]; unchanged_count: number;
}
interface VersionEntry {
  version_id: string; detected_at: string; summary: string;
  diff: VersionDiff; row_count_before: number; row_count_after: number; headers: string[];
}
interface ChangeStatus {
  change_detected: boolean; change_history: VersionEntry[];
  last_checked_at: string | null; watcher_started: boolean; poll_interval_seconds: number;
}
interface PreviewData {
  success: boolean; validation_errors: string[];
  rows_to_add: Record<string, unknown>[]; ph_headers: string[];
  duplicates_skipped: number;
  mapping_report: Array<{
    new_hub: string; source_hub: string; status: string;
    rows_inserted?: number; duplicates_skipped?: number;
  }>;
  total_to_insert: number; _elapsed_ms?: number;
}

const formatIST = (raw: string | null | undefined): string => {
  if (!raw) return "Never";
  try {
    return new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true,
    }).format(new Date(raw)) + " IST";
  } catch { return raw; }
};
const relativeTime = (raw: string): string => {
  try {
    const diff = Math.floor((Date.now() - new Date(raw).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  } catch { return ""; }
};

function VersionDiffTable({ version }: { version: VersionEntry }) {
  const { diff, headers } = version;
  const cols = headers.length > 0 ? headers : Object.keys((diff.added[0] || diff.removed[0] || {}) as Record<string,unknown>);
  const TH = () => (
    <thead>
      <tr>
        <th style={{ width: 28, padding: "5px 8px", background: "rgba(255,255,255,0.05)", borderBottom: "1px solid var(--border)", fontSize: "0.6rem", color: "var(--text-muted)" }}>#</th>
        {cols.map(c => (
          <th key={c} style={{ padding: "5px 10px", background: "rgba(255,255,255,0.05)", borderBottom: "1px solid var(--border)", fontSize: "0.62rem", fontWeight: 600, color: "var(--text-secondary)", whiteSpace: "nowrap", textTransform: "uppercase" as const, letterSpacing: "0.04em" }}>{c}</th>
        ))}
      </tr>
    </thead>
  );
  const Row = ({ row, type, changedCells, beforeVals }: { row: FFRow | Record<string,string>; type: "added"|"removed"|"modified"; changedCells?: string[]; beforeVals?: Record<string,string>; }) => {
    const bgMap = { added: "rgba(16,185,129,0.08)", removed: "rgba(239,68,68,0.08)", modified: "rgba(234,179,8,0.06)" };
    const badge = { added: { text: "+", color: "#10b981" }, removed: { text: "-", color: "#ef4444" }, modified: { text: "~", color: "#eab308" } }[type];
    return (
      <tr style={{ borderBottom: "1px solid var(--border)", background: bgMap[type] }}>
        <td style={{ padding: "4px 8px", textAlign: "center" as const, fontWeight: 700, fontSize: "0.7rem", color: badge.color }}>{badge.text}</td>
        {cols.map(c => {
          const val = String((row as Record<string,unknown>)[c] ?? "");
          const isChanged = changedCells?.includes(c);
          const oldVal = beforeVals?.[c];
          return (
            <td key={c} style={{ padding: "4px 10px", fontSize: "0.72rem", color: "var(--text-primary)", whiteSpace: "nowrap", background: isChanged ? "rgba(234,179,8,0.18)" : "transparent" }}>
              {isChanged && oldVal !== undefined ? (
                <span><span style={{ textDecoration: "line-through", color: "#ef4444", marginRight: 4, fontSize: "0.68rem" }}>{oldVal||"(empty)"}</span><span style={{ color: "#10b981", fontWeight: 600 }}>{"→ "}{val||"(empty)"}</span></span>
              ) : val}
            </td>
          );
        })}
      </tr>
    );
  };
  const hasChanges = diff.added.length + diff.removed.length + diff.modified.length > 0;
  if (!hasChanges) return <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", padding: "8px 0" }}>No row-level diff available.</p>;
  return (
    <div style={{ overflowX: "auto", borderRadius: "6px", border: "1px solid var(--border)" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.72rem" }}>
        <TH /><tbody>
          {diff.added.map((r, i) => <Row key={`a${i}`} row={r} type="added" />)}
          {diff.removed.map((r, i) => <Row key={`r${i}`} row={r} type="removed" />)}
          {diff.modified.map((m, i) => <Row key={`m${i}`} row={m.row} type="modified" changedCells={m.changed_cells} beforeVals={m.before} />)}
        </tbody>
      </table>
      <div style={{ padding: "5px 10px", background: "rgba(255,255,255,0.02)", borderTop: "1px solid var(--border)", fontSize: "0.63rem", color: "var(--text-muted)", display: "flex", gap: "1rem" }}>
        {diff.added.length > 0 && <span style={{ color: "#10b981" }}>+{diff.added.length} added</span>}
        {diff.removed.length > 0 && <span style={{ color: "#ef4444" }}>-{diff.removed.length} removed</span>}
        {diff.modified.length > 0 && <span style={{ color: "#eab308" }}>~{diff.modified.length} modified</span>}
        {diff.unchanged_count > 0 && <span>{diff.unchanged_count} unchanged</span>}
      </div>
    </div>
  );
}

// ── Task 4: Version History with batch-5 pagination ──────────────────────────
const VERSION_BATCH = 5;

function VersionHistoryPanel({ history }: { history: VersionEntry[] }) {
  const [expandedId, setExpandedId] = useState<string|null>(history.length > 0 ? history[0].version_id : null);
  const [visibleCount, setVisibleCount] = useState(VERSION_BATCH);

  if (history.length === 0) return (
    <div style={{ padding: "1.25rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.78rem" }}>
      No version history yet. Changes to FF Input will appear here automatically.
    </div>
  );

  const visibleHistory = history.slice(0, visibleCount);
  const hasMore = visibleCount < history.length;

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {visibleHistory.map((ver, idx) => {
        const isExpanded = expandedId === ver.version_id;
        const isLatest = idx === 0;
        return (
          <div key={ver.version_id} style={{ display: "flex", gap: 0 }}>
            <div style={{ width: 28, display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", flexShrink: 0, marginTop: 14, background: isLatest ? "#a855f7" : "var(--text-muted)", border: isLatest ? "2px solid rgba(168,85,247,0.4)" : "2px solid var(--border)", boxShadow: isLatest ? "0 0 8px rgba(168,85,247,0.4)" : "none" }} />
              {idx < visibleHistory.length - 1 && <div style={{ width: 1, flex: 1, background: "var(--border)", margin: "2px 0" }} />}
            </div>
            <div style={{ flex: 1, marginBottom: 8, paddingLeft: 8 }}>
              <button type="button" onClick={() => setExpandedId(isExpanded ? null : ver.version_id)} style={{ width: "100%", textAlign: "left", background: "transparent", border: "none", cursor: "pointer", padding: "8px 0 4px", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-primary)" }}>{formatIST(ver.detected_at)}</span>
                    {isLatest && <span style={{ fontSize: "0.6rem", padding: "1px 5px", borderRadius: "4px", background: "rgba(168,85,247,0.15)", color: "#a855f7", fontWeight: 700 }}>Latest</span>}
                  </div>
                  <div style={{ display: "flex", gap: 8, marginTop: 2 }}>
                    <span style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>{ver.summary}</span>
                    <span style={{ fontSize: "0.63rem", color: "var(--text-muted)" }}>- {relativeTime(ver.detected_at)}</span>
                  </div>
                  <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                    {ver.diff.added.length > 0 && <span style={{ fontSize: "0.6rem", padding: "1px 5px", borderRadius: "3px", background: "rgba(16,185,129,0.1)", color: "#10b981", fontWeight: 600 }}>+{ver.diff.added.length} added</span>}
                    {ver.diff.removed.length > 0 && <span style={{ fontSize: "0.6rem", padding: "1px 5px", borderRadius: "3px", background: "rgba(239,68,68,0.1)", color: "#ef4444", fontWeight: 600 }}>-{ver.diff.removed.length} removed</span>}
                    {ver.diff.modified.length > 0 && <span style={{ fontSize: "0.6rem", padding: "1px 5px", borderRadius: "3px", background: "rgba(234,179,8,0.1)", color: "#eab308", fontWeight: 600 }}>~{ver.diff.modified.length} modified</span>}
                    <span style={{ fontSize: "0.6rem", color: "var(--text-muted)", padding: "1px 5px" }}>{ver.row_count_before} → {ver.row_count_after} rows</span>
                  </div>
                </div>
                {isExpanded ? <ChevronUp size={13} style={{ color: "var(--text-muted)", marginTop: 4, flexShrink: 0 }} /> : <ChevronDown size={13} style={{ color: "var(--text-muted)", marginTop: 4, flexShrink: 0 }} />}
              </button>
              {isExpanded && <div style={{ marginBottom: 8 }}><VersionDiffTable version={ver} /></div>}
            </div>
          </div>
        );
      })}

      {/* Load More / Show Less controls */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, paddingTop: 4, paddingLeft: 28 }}>
        {hasMore && (
          <button
            type="button"
            onClick={() => setVisibleCount(c => c + VERSION_BATCH)}
            style={{
              fontSize: "0.7rem", padding: "4px 12px", borderRadius: "6px",
              border: "1px solid var(--border)", background: "var(--bg-elevated)",
              color: "var(--text-secondary)", cursor: "pointer",
              display: "flex", alignItems: "center", gap: 4,
              transition: "background 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
            onMouseLeave={e => (e.currentTarget.style.background = "var(--bg-elevated)")}
          >
            <ChevronDown size={11} />
            Load {Math.min(VERSION_BATCH, history.length - visibleCount)} more
            <span style={{ fontSize: "0.6rem", color: "var(--text-muted)" }}>({history.length - visibleCount} remaining)</span>
          </button>
        )}
        {visibleCount > VERSION_BATCH && (
          <button
            type="button"
            onClick={() => setVisibleCount(VERSION_BATCH)}
            style={{
              fontSize: "0.7rem", padding: "4px 10px", borderRadius: "6px",
              border: "1px solid var(--border)", background: "transparent",
              color: "var(--text-muted)", cursor: "pointer",
              transition: "background 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.04)")}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
          >
            Collapse
          </button>
        )}
        {!hasMore && history.length > VERSION_BATCH && (
          <span style={{ fontSize: "0.63rem", color: "var(--text-muted)" }}>All {history.length} versions shown</span>
        )}
      </div>
    </div>
  );
}

// ── Task 2: Add Hub Modal ─────────────────────────────────────────────────────
interface AddHubModalProps {
  headers?: string[];
  onClose: () => void;
  onSuccess: () => void;
}

function AddHubModal({ headers, onClose, onSuccess }: AddHubModalProps) {
  const finalHeaders = (headers && headers.length > 0)
    ? headers
    : ['city_name', 'Type', 'Hub_name', 'Hub_id', 'Source_Hub', 'Percentage', 'Start_date', 'End_date'];

  const [form, setForm] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    finalHeaders.forEach(h => {
      if (h.toLowerCase() === "type") {
        init[h] = "New Hub Launch";
      } else {
        init[h] = "";
      }
    });
    return init;
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Basic client-side validation
    for (const h of finalHeaders) {
      const val = form[h]?.trim() ?? "";
      const hLower = h.toLowerCase();
      if (!val) {
        setError(`"${h}" is required.`);
        return;
      }
      if (hLower === "percentage") {
        const pct = parseFloat(val);
        if (isNaN(pct) || pct < 0 || pct > 1) {
          setError('"Percentage" must be a number between 0 and 1 (e.g. 0.5 or 0.001).');
          return;
        }
      }
      if (hLower === "hub_id" || hLower === "hubid" || hLower === "hub id") {
        if (!/^\d+$/.test(val)) {
          setError('Hub ID must contain numbers only.');
          return;
        }
      }
    }

    const startDateKey = finalHeaders.find(h => h.toLowerCase().replace(/[\s_]/g, "") === "startdate") || "";
    const endDateKey = finalHeaders.find(h => h.toLowerCase().replace(/[\s_]/g, "") === "enddate") || "";
    const startDateVal = form[startDateKey]?.trim() ?? "";
    const endDateVal = form[endDateKey]?.trim() ?? "";
    if (startDateVal && endDateVal) {
      if (new Date(startDateVal) > new Date(endDateVal)) {
        setError("Start Date must be less than or equal to End Date.");
        return;
      }
    }

    setError("");
    setSubmitting(true);
    try {
      await api.post("/api/new-product-launch/sync-new-hub/ff-input/append", { row: form });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || "Failed to add hub. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const getInputType = (h: string) => {
    const norm = h.toLowerCase().replace(/[\s_]/g, "");
    if (norm.includes("date")) return "date";
    if (norm.includes("percentage") || norm.includes("percent")) return "number";
    if (norm.includes("id")) return "number";
    return "text";
  };

  const getPlaceholder = (h: string) => {
    const norm = h.toLowerCase().replace(/[\s_]/g, "");
    if (norm.includes("percentage")) return "Between 0.0 and 1.0 (e.g. 0.001)";
    if (norm.includes("id")) return "Numeric Hub ID (e.g. 2606)";
    if (norm.includes("city")) return "e.g. NCR";
    if (norm.includes("source")) return "e.g. NGC";
    if (norm.includes("hub")) return "e.g. AGC";
    return `Enter ${h}`;
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
    }}>
      <div style={{
        background: "#ffffff", border: "1px solid #e2e8f0",
        borderRadius: "12px", width: "100%", maxWidth: 540,
        boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
        display: "flex", flexDirection: "column", maxHeight: "90vh",
        animation: "fadeInScale 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
        color: "#1e293b"
      }}>
        {/* Header */}
        <div style={{
          padding: "1.25rem 1.5rem", borderBottom: "1px solid #e2e8f0",
          display: "flex", alignItems: "center", gap: 12,
          background: "#f8fafc", borderTopLeftRadius: "12px", borderTopRightRadius: "12px"
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: "8px",
            background: "rgba(124, 58, 237, 0.08)",
            border: "1px solid rgba(124, 58, 237, 0.15)",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>
            <Plus size={16} style={{ color: "#7c3aed" }} />
          </div>
          <div style={{ flex: 1 }}>
            <h3 style={{ margin: 0, fontWeight: 600, fontSize: "0.95rem", color: "#0f172a" }}>Add New Hub Config</h3>
            <p style={{ margin: 0, fontSize: "0.72rem", color: "#64748b" }}>Append a validated row to the FF Input sheet</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: "transparent", border: "none",
              cursor: "pointer", color: "#64748b", padding: "6px", borderRadius: "8px",
              transition: "all 0.15s", display: "flex", alignItems: "center", justifyContent: "center"
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = "#f1f5f9";
              e.currentTarget.style.color = "#0f172a";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "#64748b";
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} style={{ overflowY: "auto", flex: 1, display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {error && (
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "0.75rem 1rem", borderRadius: "6px",
                background: "#fef2f2", border: "1px solid #fee2e2",
                fontSize: "0.78rem", color: "#b91c1c",
              }}>
                <XCircle size={14} style={{ flexShrink: 0 }} />
                <span>{error}</span>
              </div>
            )}
            
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
              {finalHeaders.map(header => {
                const isTypeField = header.toLowerCase() === "type";
                const isFullWidth = ["hub_name", "source_hub"].includes(header.toLowerCase());
                const type = getInputType(header);
                
                return (
                  <div key={header} style={{ gridColumn: isFullWidth ? "span 2" : "auto" }}>
                    <label style={{
                      display: "flex", alignItems: "center", gap: 4,
                      fontSize: "0.75rem", fontWeight: 600,
                      color: "#475569",
                      marginBottom: "0.35rem",
                    }}>
                      {header.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
                      <span style={{ color: "#ef4444", fontSize: "0.75rem" }}>*</span>
                    </label>
                    
                    {isTypeField ? (
                      <select
                        value={form[header] ?? "New Hub Launch"}
                        onChange={e => setForm(prev => ({ ...prev, [header]: e.target.value }))}
                        className="form-input"
                        style={{
                          width: "100%", boxSizing: "border-box", fontSize: "0.82rem",
                          background: "#ffffff", border: "1px solid #cbd5e1",
                          borderRadius: "6px", color: "#0f172a", padding: "0.5rem 0.75rem",
                          outline: "none"
                        }}
                      >
                        <option value="New Hub Launch">New Hub Launch</option>
                        <option value="KML Remapping">KML Remapping</option>
                      </select>
                    ) : (
                      <input
                        type={type}
                        step={type === "number" && header.toLowerCase().includes("percentage") ? "any" : "1"}
                        min={type === "number" && header.toLowerCase().includes("percentage") ? "0" : undefined}
                        max={type === "number" && header.toLowerCase().includes("percentage") ? "1" : undefined}
                        value={form[header] ?? ""}
                        onChange={e => setForm(prev => ({ ...prev, [header]: e.target.value }))}
                        placeholder={getPlaceholder(header)}
                        className="form-input"
                        style={{
                          width: "100%", boxSizing: "border-box", fontSize: "0.82rem",
                          background: "#ffffff", border: "1px solid #cbd5e1",
                          borderRadius: "6px", color: "#0f172a", padding: "0.5rem 0.75rem",
                          transition: "border-color 0.15s, box-shadow 0.15s",
                          outline: "none"
                        }}
                        onFocus={e => {
                          e.currentTarget.style.borderColor = "#7c3aed";
                          e.currentTarget.style.boxShadow = "0 0 0 3px rgba(124, 58, 237, 0.1)";
                        }}
                        onBlur={e => {
                          e.currentTarget.style.borderColor = "#cbd5e1";
                          e.currentTarget.style.boxShadow = "none";
                        }}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Footer */}
          <div style={{
            padding: "1rem 1.5rem", borderTop: "1px solid #e2e8f0",
            display: "flex", gap: 10, justifyContent: "flex-end",
            background: "#f8fafc", borderBottomLeftRadius: "12px", borderBottomRightRadius: "12px"
          }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onClose}
              disabled={submitting}
              style={{
                borderRadius: "6px", padding: "0.5rem 1rem", fontSize: "0.8rem",
                background: "#ffffff", border: "1px solid #cbd5e1", color: "#475569"
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = "#f8fafc";
                e.currentTarget.style.color = "#0f172a";
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = "#ffffff";
                e.currentTarget.style.color = "#475569";
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "0.5rem 1.25rem", borderRadius: "6px", border: "none",
                background: "#7c3aed",
                color: "#fff", fontWeight: 600, fontSize: "0.8rem",
                cursor: submitting ? "not-allowed" : "pointer",
                boxShadow: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
                opacity: submitting ? 0.7 : 1, transition: "all 0.15s",
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = "#6d28d9";
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = "#7c3aed";
              }}
            >
              {submitting ? <RefreshCw size={13} className="animate-spin" /> : <Plus size={13} />}
              {submitting ? "Adding…" : "Add Hub Config"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


// ── SkuVersionHistoryPanel ──────────────────────────────────────────────────
function SkuVersionHistoryPanel({ history }: { history: VersionEntry[] }) {
  const [expandedId, setExpandedId] = useState<string|null>(history.length > 0 ? history[0].version_id : null);
  const [visibleCount, setVisibleCount] = useState(VERSION_BATCH);

  if (history.length === 0) return (
    <div style={{ padding: "1.25rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.78rem" }}>
      No version history yet. Changes to Hub SKU Master will appear here automatically.
    </div>
  );

  const visibleHistory = history.slice(0, visibleCount);
  const hasMore = visibleCount < history.length;

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {visibleHistory.map((ver, idx) => {
        const isExpanded = expandedId === ver.version_id;
        const isLatest = idx === 0;
        return (
          <div key={ver.version_id} style={{ display: "flex", gap: 0 }}>
            <div style={{ width: 28, display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", flexShrink: 0, marginTop: 14, background: isLatest ? "#a855f7" : "var(--text-muted)", border: isLatest ? "2px solid rgba(168,85,247,0.4)" : "2px solid var(--border)", boxShadow: isLatest ? "0 0 8px rgba(168,85,247,0.4)" : "none" }} />
              {idx < visibleHistory.length - 1 && <div style={{ width: 1, flex: 1, background: "var(--border)", margin: "2px 0" }} />}
            </div>
            <div style={{ flex: 1, marginBottom: 8, paddingLeft: 8 }}>
              <button type="button" onClick={() => setExpandedId(isExpanded ? null : ver.version_id)} style={{ width: "100%", textAlign: "left", background: "transparent", border: "none", cursor: "pointer", padding: "8px 0 4px", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-primary)" }}>{formatIST(ver.detected_at)}</span>
                    {isLatest && <span style={{ fontSize: "0.6rem", padding: "1px 5px", borderRadius: "4px", background: "rgba(168,85,247,0.15)", color: "#a855f7", fontWeight: 700 }}>Latest</span>}
                  </div>
                  <div style={{ display: "flex", gap: 8, marginTop: 2 }}>
                    <span style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>{ver.summary}</span>
                    <span style={{ fontSize: "0.63rem", color: "var(--text-muted)" }}>- {relativeTime(ver.detected_at)}</span>
                  </div>
                  <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                    {ver.diff.added.length > 0 && <span style={{ fontSize: "0.6rem", padding: "1px 5px", borderRadius: "3px", background: "rgba(16,185,129,0.1)", color: "#10b981", fontWeight: 600 }}>+{ver.diff.added.length} added</span>}
                    {ver.diff.removed.length > 0 && <span style={{ fontSize: "0.6rem", padding: "1px 5px", borderRadius: "3px", background: "rgba(239,68,68,0.1)", color: "#ef4444", fontWeight: 600 }}>-{ver.diff.removed.length} removed</span>}
                    {ver.diff.modified.length > 0 && <span style={{ fontSize: "0.6rem", padding: "1px 5px", borderRadius: "3px", background: "rgba(234,179,8,0.1)", color: "#eab308", fontWeight: 600 }}>~{ver.diff.modified.length} modified</span>}
                    <span style={{ fontSize: "0.6rem", color: "var(--text-muted)", padding: "1px 5px" }}>{ver.row_count_before} → {ver.row_count_after} rows</span>
                  </div>
                </div>
                {isExpanded ? <ChevronUp size={13} style={{ color: "var(--text-muted)", marginTop: 4, flexShrink: 0 }} /> : <ChevronDown size={13} style={{ color: "var(--text-muted)", marginTop: 4, flexShrink: 0 }} />}
              </button>
              {isExpanded && <div style={{ marginBottom: 8 }}><VersionDiffTable version={ver} /></div>}
            </div>
          </div>
        );
      })}

      <div style={{ display: "flex", alignItems: "center", gap: 8, paddingTop: 4, paddingLeft: 28 }}>
        {hasMore && (
          <button
            type="button"
            onClick={() => setVisibleCount(c => c + VERSION_BATCH)}
            style={{
              fontSize: "0.7rem", padding: "4px 12px", borderRadius: "6px",
              border: "1px solid var(--border)", background: "var(--bg-elevated)",
              color: "var(--text-secondary)", cursor: "pointer",
              display: "flex", alignItems: "center", gap: 4,
              transition: "background 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
            onMouseLeave={e => (e.currentTarget.style.background = "var(--bg-elevated)")}
          >
            <ChevronDown size={11} />
            Load {Math.min(VERSION_BATCH, history.length - visibleCount)} more
            <span style={{ fontSize: "0.6rem", color: "var(--text-muted)" }}>({history.length - visibleCount} remaining)</span>
          </button>
        )}
        {visibleCount > VERSION_BATCH && (
          <button
            type="button"
            onClick={() => setVisibleCount(VERSION_BATCH)}
            style={{
              fontSize: "0.7rem", padding: "4px 10px", borderRadius: "6px",
              border: "1px solid var(--border)", background: "transparent",
              color: "var(--text-muted)", cursor: "pointer",
              transition: "background 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.04)")}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
          >
            Collapse
          </button>
        )}
        {!hasMore && history.length > VERSION_BATCH && (
          <span style={{ fontSize: "0.63rem", color: "var(--text-muted)" }}>All {history.length} versions shown</span>
        )}
      </div>
    </div>
  );
}

// ── AddSkuModal ─────────────────────────────────────────────────────────────
interface AddSkuModalProps {
  headers?: string[];
  onClose: () => void;
  onSuccess: () => void;
}

function AddSkuModal({ headers, onClose, onSuccess }: AddSkuModalProps) {
  const finalHeaders = (headers && headers.length > 0)
    ? headers
    : [
        'Channel', 'city_name', 'hub_name', 'sub category', 'sku class prod',
        'HTT', 'Hub active', 'Plan Flag',
        'Active_Flag_Mon', 'Active_Flag_Tue', 'Active_Flag_Wed',
        'Active_Flag_Thu', 'Active_Flag_Fri', 'Active_Flag_Sat', 'Active_Flag_Sun'
      ];

  const [form, setForm] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    finalHeaders.forEach(h => {
      const hLower = h.toLowerCase().trim().replace(/_/g, " ");
      if (hLower === "channel") {
        init[h] = "Online";
      } else if (hLower === "htt") {
        init[h] = "tail";
      } else if (hLower === "hub active") {
        init[h] = "1";
      } else if (hLower === "plan flag") {
        init[h] = "A";
      } else if (hLower.startsWith("active flag")) {
        init[h] = "1";
      } else {
        init[h] = "";
      }
    });
    return init;
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    for (const h of finalHeaders) {
      const val = form[h]?.trim() ?? "";
      const hLower = h.toLowerCase().trim().replace(/_/g, " ");
      if (!val) {
        setError(`"${h}" is required.`);
        return;
      }
      if (hLower === "plan flag") {
        if (val.toUpperCase() !== "A" && val.toUpperCase() !== "I") {
          setError('"Plan Flag" must be "A" or "I".');
          return;
        }
      }
      if (hLower === "hub active" || hLower.startsWith("active flag")) {
        if (!/^\d+$/.test(val)) {
          setError(`"${h}" must contain numbers only.`);
          return;
        }
      }
    }

    setError("");
    setSubmitting(true);
    try {
      await api.post("/api/new-product-launch/sync-new-hub/hub-sku-master/append", { row: form });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || "Failed to add SKU configuration. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
    }}>
      <div style={{
        background: "#ffffff", border: "1px solid #e2e8f0",
        borderRadius: "12px", width: "100%", maxWidth: 640,
        boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
        display: "flex", flexDirection: "column", maxHeight: "90vh",
        animation: "fadeInScale 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
        color: "#1e293b"
      }}>
        <div style={{
          padding: "1.25rem 1.5rem", borderBottom: "1px solid #e2e8f0",
          display: "flex", alignItems: "center", gap: 12,
          background: "#f8fafc", borderTopLeftRadius: "12px", borderTopRightRadius: "12px"
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: "8px",
            background: "rgba(124, 58, 237, 0.08)",
            border: "1px solid rgba(124, 58, 237, 0.15)",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>
            <Plus size={16} style={{ color: "#7c3aed" }} />
          </div>
          <div style={{ flex: 1 }}>
            <h3 style={{ margin: 0, fontWeight: 600, fontSize: "0.95rem", color: "#0f172a" }}>Add New SKU Mapping</h3>
            <p style={{ margin: 0, fontSize: "0.72rem", color: "#64748b" }}>Append a validated row to the Hub SKU Master sheet</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: "transparent", border: "none",
              cursor: "pointer", color: "#64748b", padding: "6px", borderRadius: "8px",
              transition: "all 0.15s", display: "flex", alignItems: "center", justifyContent: "center"
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = "#f1f5f9";
              e.currentTarget.style.color = "#0f172a";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "#64748b";
            }}
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ overflowY: "auto", flex: 1, display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {error && (
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "0.75rem 1rem", borderRadius: "6px",
                background: "#fef2f2", border: "1px solid #fee2e2",
                fontSize: "0.78rem", color: "#b91c1c",
              }}>
                <XCircle size={14} style={{ flexShrink: 0 }} />
                <span>{error}</span>
              </div>
            )}
            
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
              {finalHeaders.map(header => {
                const isDropdown = ["channel", "htt", "plan flag"].includes(header.toLowerCase().trim().replace(/_/g, " "));
                const isFullWidth = ["sku class prod"].includes(header.toLowerCase().trim().replace(/_/g, " "));
                
                return (
                  <div key={header} style={{ gridColumn: isFullWidth ? "span 2" : "auto" }}>
                    <label style={{
                      display: "flex", alignItems: "center", gap: 4,
                      fontSize: "0.72rem", fontWeight: 600,
                      color: "#475569",
                      marginBottom: "0.25rem",
                    }}>
                      {header.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
                      <span style={{ color: "#ef4444", fontSize: "0.75rem" }}>*</span>
                    </label>
                    
                    {isDropdown ? (
                      <select
                        value={form[header] ?? ""}
                        onChange={e => setForm(prev => ({ ...prev, [header]: e.target.value }))}
                        className="form-input"
                        style={{
                          width: "100%", boxSizing: "border-box", fontSize: "0.82rem",
                          background: "#ffffff", border: "1px solid #cbd5e1",
                          borderRadius: "6px", color: "#0f172a", padding: "0.4rem 0.6rem",
                          outline: "none"
                        }}
                      >
                        {header.toLowerCase().trim().replace(/_/g, " ") === "channel" ? (
                          <>
                            <option value="Online">Online</option>
                            <option value="Store">Store</option>
                            <option value="All">All</option>
                          </>
                        ) : header.toLowerCase().trim().replace(/_/g, " ") === "plan flag" ? (
                          <>
                            <option value="A">Active (A)</option>
                            <option value="I">Inactive (I)</option>
                          </>
                        ) : (
                          <>
                            <option value="tail">tail</option>
                            <option value="head">head</option>
                          </>
                        )}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={form[header] ?? ""}
                        onChange={e => setForm(prev => ({ ...prev, [header]: e.target.value }))}
                        placeholder={`Enter ${header}`}
                        className="form-input"
                        style={{
                          width: "100%", boxSizing: "border-box", fontSize: "0.82rem",
                          background: "#ffffff", border: "1px solid #cbd5e1",
                          borderRadius: "6px", color: "#0f172a", padding: "0.4rem 0.6rem",
                          transition: "border-color 0.15s, box-shadow 0.15s",
                          outline: "none"
                        }}
                        onFocus={e => {
                          e.currentTarget.style.borderColor = "#7c3aed";
                          e.currentTarget.style.boxShadow = "0 0 0 3px rgba(124, 58, 237, 0.1)";
                        }}
                        onBlur={e => {
                          e.currentTarget.style.borderColor = "#cbd5e1";
                          e.currentTarget.style.boxShadow = "none";
                        }}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div style={{
            padding: "1rem 1.5rem", borderTop: "1px solid #e2e8f0",
            display: "flex", gap: 10, justifyContent: "flex-end",
            background: "#f8fafc", borderBottomLeftRadius: "12px", borderBottomRightRadius: "12px"
          }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onClose}
              disabled={submitting}
              style={{
                borderRadius: "6px", padding: "0.5rem 1rem", fontSize: "0.8rem",
                background: "#ffffff", border: "1px solid #cbd5e1", color: "#475569"
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = "#f8fafc";
                e.currentTarget.style.color = "#0f172a";
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = "#ffffff";
                e.currentTarget.style.color = "#475569";
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "0.5rem 1.25rem", borderRadius: "6px", border: "none",
                background: "#7c3aed",
                color: "#fff", fontWeight: 600, fontSize: "0.8rem",
                cursor: submitting ? "not-allowed" : "pointer",
                boxShadow: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
                opacity: submitting ? 0.7 : 1, transition: "all 0.15s",
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = "#6d28d9";
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = "#7c3aed";
              }}
            >
              {submitting ? <RefreshCw size={13} className="animate-spin" /> : <Plus size={13} />}
              {submitting ? "Adding…" : "Add SKU Mapping"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main HubLaunchTab ─────────────────────────────────────────────────────────
export default function HubLaunchTab() {
  const { canWrite } = useAuth();
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [syncedCount, setSyncedCount] = useState(0);
  const [syncSuccess, setSyncSuccess] = useState(false);
  const [ffData, setFfData] = useState<FFInputData | null>(null);
  const [loadingFf, setLoadingFf] = useState(false);
  const [changeStatus, setChangeStatus] = useState<ChangeStatus | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  // Task 2: Add Hub modal state
  const [showAddHub, setShowAddHub] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<{ ts: string | null; user_id: string | null } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Hub SKU Master replica state variables
  const [skuData, setSkuData] = useState<FFInputData | null>(null);
  const [loadingSku, setLoadingSku] = useState(false);
  const [skuChangeStatus, setSkuChangeStatus] = useState<ChangeStatus | null>(null);
  const [showSkuHistory, setShowSkuHistory] = useState(false);
  const [showAddSku, setShowAddSku] = useState(false);
  const [skuLastUpdate, setSkuLastUpdate] = useState<{ ts: string | null; user_id: string | null } | null>(null);
  const skuPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchFFInput = useCallback(async (bypass: boolean) => {
    setLoadingFf(true);
    const t0 = performance.now();
    try {
      const { data } = await api.get<FFInputData>(`/api/new-product-launch/sync-new-hub/ff-input?bypass_cache=${bypass}`);
      console.info(`[HubLaunchTab] FF Input: ${data.row_count} rows in ${Math.round(performance.now()-t0)}ms`);
      setFfData(data);
    } catch(e) { console.error("[HubLaunchTab] FF Input failed:", e); }
    finally { setLoadingFf(false); }
  }, []);

  const fetchChangeStatus = useCallback(async () => {
    try {
      const { data } = await api.get<ChangeStatus>("/api/new-product-launch/sync-new-hub/change-status");
      setChangeStatus(data);
    } catch(e) { console.warn("[HubLaunchTab] change-status poll failed:", e); }
  }, []);

  const fetchLastUpdate = useCallback(async () => {
    try {
      const { data } = await api.get<{ ts: string | null; user_id: string | null }>("/api/new-product-launch/sync-new-hub/last-update");
      setLastUpdate(data);
    } catch(e) { console.warn("[HubLaunchTab] Failed to fetch last update:", e); }
  }, []);

  useEffect(() => {
    fetchFFInput(false);
    fetchChangeStatus();
    fetchLastUpdate();
    // Task 3: Reduced from 30_000ms → 15_000ms
    pollRef.current = setInterval(fetchChangeStatus, 15_000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchFFInput, fetchChangeStatus, fetchLastUpdate]);

  // Hub SKU Master data fetching callbacks
  const fetchSkuMaster = useCallback(async (bypass: boolean) => {
    setLoadingSku(true);
    const t0 = performance.now();
    try {
      const { data } = await api.get<FFInputData>(`/api/new-product-launch/sync-new-hub/hub-sku-master?bypass_cache=${bypass}`);
      console.info(`[HubLaunchTab] SKU Master: ${data.row_count} rows in ${Math.round(performance.now()-t0)}ms`);
      setSkuData(data);
    } catch(e) { console.error("[HubLaunchTab] Hub SKU Master fetch failed:", e); }
    finally { setLoadingSku(false); }
  }, []);

  const fetchSkuChangeStatus = useCallback(async () => {
    try {
      const { data } = await api.get<ChangeStatus>("/api/new-product-launch/sync-new-hub/hub-sku-master/change-status");
      setSkuChangeStatus(data);
    } catch(e) { console.warn("[HubLaunchTab] SKU change-status poll failed:", e); }
  }, []);

  const fetchSkuLastUpdate = useCallback(async () => {
    try {
      const { data } = await api.get<{ ts: string | null; user_id: string | null }>("/api/new-product-launch/sync-new-hub/hub-sku-master/last-update");
      setSkuLastUpdate(data);
    } catch(e) { console.warn("[HubLaunchTab] Failed to fetch SKU last update:", e); }
  }, []);

  const dismissSkuChanges = async () => {
    try {
      await api.post("/api/new-product-launch/sync-new-hub/hub-sku-master/dismiss-changes", {});
      setSkuChangeStatus(prev => prev ? { ...prev, change_detected: false } : prev);
    } catch(e) { console.error("[HubLaunchTab] SKU dismiss failed:", e); }
  };

  useEffect(() => {
    fetchSkuMaster(false);
    fetchSkuChangeStatus();
    fetchSkuLastUpdate();
    skuPollRef.current = setInterval(fetchSkuChangeStatus, 15_000);
    return () => { if (skuPollRef.current) clearInterval(skuPollRef.current); };
  }, [fetchSkuMaster, fetchSkuChangeStatus, fetchSkuLastUpdate]);

  const fetchPreview = async (bypassCache: boolean) => {
    setRunning(true); setMsg({ text: "", type: "" }); setPreview(null);
    const t0 = performance.now();
    try {
      const { data } = await api.get<PreviewData>(`/api/new-product-launch/sync-new-hub/preview?bypass_cache=${bypassCache}`);
      const el = Math.round(performance.now()-t0);
      setPreview(data); setShowPreview(true);
      if (data.validation_errors.length > 0) {
        setMsg({ text: `${data.validation_errors.length} Hub Mapping issue(s) found. Resolve in Google Sheets first.`, type: "warning" });
      } else {
        setMsg({ text: `Preview loaded: ${data.total_to_insert} rows to sync, ${data.duplicates_skipped} skipped - ${el}ms`, type: "success" });
      }
    } catch(e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Failed to load preview.", type: "danger" });
    } finally { setRunning(false); }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setRunning(true); setMsg({ text: "", type: "" });
    const t0 = performance.now();
    try {
      const { data } = await api.post("/api/new-product-launch/sync-new-hub/confirm", { rows_to_add: preview.rows_to_add, ph_headers: preview.ph_headers });
      const el = Math.round(performance.now()-t0);
      setSyncedCount(data.rows_inserted); setSyncSuccess(true);
      setMsg({ text: `${data.detail || "Synced."} - ${el}ms`, type: "success" });
    } catch(e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Sync failed", type: "danger" });
    } finally { setRunning(false); }
  };

  const dismissChanges = async () => {
    try {
      await api.post("/api/new-product-launch/sync-new-hub/dismiss-changes", {});
      setChangeStatus(prev => prev ? { ...prev, change_detected: false } : prev);
    } catch(e) { console.error("[HubLaunchTab] dismiss failed:", e); }
  };

  const hasChanges = changeStatus?.change_detected ?? false;
  const history = changeStatus?.change_history ?? [];

  return (
    <div className="w-full max-w-5xl space-y-4">

      {/* Add Hub Modal — Task 2 */}
      {showAddHub && (
        <AddHubModal
          headers={ffData?.headers}
          onClose={() => setShowAddHub(false)}
          onSuccess={() => { fetchFFInput(true); fetchLastUpdate(); }}
        />
      )}

      {/* Add Sku Modal */}
      {showAddSku && (
        <AddSkuModal
          headers={skuData?.headers}
          onClose={() => setShowAddSku(false)}
          onSuccess={() => { fetchSkuMaster(true); fetchSkuLastUpdate(); }}
        />
      )}

      {hasChanges && (
        <div style={{ background: "rgba(168,85,247,0.07)", border: "1px solid rgba(168,85,247,0.35)", borderRadius: "12px", padding: "0.9rem 1rem" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <Bell size={16} style={{ color: "#a855f7", marginTop: 2, flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <strong style={{ fontSize: "0.83rem", color: "var(--text-primary)" }}>FF Input Sheet Changed</strong>
                {history.length > 0 && <span style={{ fontSize: "0.62rem", padding: "1px 6px", borderRadius: "4px", background: "rgba(168,85,247,0.15)", color: "#a855f7", fontWeight: 700 }}>{history[0].summary}</span>}
                {history.length > 0 && <span style={{ fontSize: "0.63rem", color: "var(--text-muted)" }}>{relativeTime(history[0].detected_at)}</span>}
              </div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", margin: "0 0 8px" }}>The FF Input configuration was updated. Update Masters before syncing. Email alert has been sent.</p>
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" onClick={() => { setShowHistory(true); dismissChanges(); }} style={{ fontSize: "0.72rem", padding: "4px 12px", background: "#a855f7", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                  <ArrowLeftRight size={11} /> View Version History
                </button>
                <button type="button" className="btn btn-sm btn-ghost" style={{ fontSize: "0.72rem", padding: "4px 12px", height: "auto" }} onClick={dismissChanges}>Dismiss</button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div style={{ background: "rgba(234,179,8,0.06)", border: "1px solid rgba(234,179,8,0.3)", borderRadius: "12px", padding: "0.7rem 1rem", display: "flex", alignItems: "flex-start", gap: 10 }}>
        <Bell size={14} style={{ color: "#eab308", marginTop: 1, flexShrink: 0 }} />
        <div style={{ fontSize: "0.78rem" }}>
          <strong style={{ color: "var(--text-primary)" }}>Update Masters Before Syncing - </strong>
          <span style={{ color: "var(--text-secondary)" }}>Ensure Hub Mapping, P-H Master, and FF Input tabs are current.</span>
        </div>
      </div>

      {/* FF Input Sheet Table */}
      <div className="card" style={{ borderRadius: "12px", padding: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", flexDirection: "column", padding: "0.65rem 1rem", borderBottom: "1px solid var(--border)", background: "rgba(255,255,255,0.02)", gap: 6 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Database size={14} style={{ color: "var(--blue)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.8rem", color: "var(--text-primary)" }}>FF Input Sheet</span>
              {ffData && <span style={{ fontSize: "0.62rem", padding: "1px 6px", borderRadius: "4px", background: "rgba(59,130,246,0.1)", color: "var(--blue)", fontWeight: 600 }}>{ffData.row_count} rows</span>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {/* Task 2: Add Hub CRM button */}
              {canWrite && (
                <button
                  type="button"
                  onClick={() => setShowAddHub(true)}
                  style={{
                    fontSize: "0.78rem", padding: "6px 14px", height: "auto",
                    display: "flex", alignItems: "center", gap: 5,
                    background: "linear-gradient(135deg, rgba(168,85,247,0.15), rgba(99,102,241,0.12))",
                    border: "1px solid rgba(168,85,247,0.35)", borderRadius: "8px",
                    color: "#a855f7", fontWeight: 600, cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = "linear-gradient(135deg, rgba(168,85,247,0.25), rgba(99,102,241,0.2))";
                    e.currentTarget.style.borderColor = "rgba(168,85,247,0.55)";
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = "linear-gradient(135deg, rgba(168,85,247,0.15), rgba(99,102,241,0.12))";
                    e.currentTarget.style.borderColor = "rgba(168,85,247,0.35)";
                  }}
                >
                  <Plus size={12} />
                  Add Hub
                </button>
              )}

              <button type="button" className="btn btn-sm btn-ghost" style={{ fontSize: "0.68rem", padding: "4px 10px", height: "auto", display: "flex", alignItems: "center", gap: 3 }} onClick={() => fetchFFInput(true)} disabled={loadingFf}>
                <RefreshCw size={10} className={loadingFf ? "animate-spin" : ""} /> {loadingFf ? "Fetching..." : "Refresh Live"}
              </button>
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.64rem", color: "var(--text-muted)", flexWrap: "wrap", gap: 8, borderTop: "1px solid rgba(255,255,255,0.03)", paddingTop: "6px" }}>
            {lastUpdate && lastUpdate.ts ? (
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <Clock size={10} />
                Last updated by : <strong style={{ color: "var(--text-secondary)" }}>{lastUpdate.user_id}</strong> at {formatIST(lastUpdate.ts)}
              </span>
            ) : (
              <span />
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              {changeStatus?.last_checked_at && <span style={{ fontSize: "0.6rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 3 }}><Clock size={9} /> Checked {relativeTime(changeStatus.last_checked_at)}</span>}
              {ffData?.cache_last_updated && <span style={{ fontSize: "0.6rem", color: "var(--text-muted)" }}>Cached: {formatIST(ffData.cache_last_updated)}</span>}
            </div>
          </div>
        </div>
        {loadingFf && !ffData ? (
          <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.78rem" }}><RefreshCw size={13} className="animate-spin inline mr-2" />Loading FF Input...</div>
        ) : ffData && ffData.rows.length > 0 ? (
          <div style={{ overflowX: "auto", maxHeight: "210px", overflowY: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.71rem" }}>
              <thead><tr style={{ background: "rgba(255,255,255,0.04)", borderBottom: "1px solid var(--border)", position: "sticky", top: 0 }}>{ffData.headers.map(h => <th key={h} style={{ padding: "0.38rem 0.75rem", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)", whiteSpace: "nowrap", textTransform: "uppercase", letterSpacing: "0.04em", fontSize: "0.62rem" }}>{h}</th>)}</tr></thead>
              <tbody>{ffData.rows.map((row, i) => <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>{ffData.headers.map(h => <td key={h} style={{ padding: "0.33rem 0.75rem", color: "var(--text-primary)", whiteSpace: "nowrap" }}>{String(row[h] ?? "")}</td>)}</tr>)}</tbody>
            </table>
          </div>
        ) : (
          <div style={{ padding: "1.25rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.78rem" }}>No FF Input rows. Click Refresh Live to fetch from sheet.</div>
        )}
      </div>

      {/* Version History — Task 4: batch-5 pagination */}
      <div className="card" style={{ borderRadius: "12px", padding: 0, overflow: "hidden" }}>
        <button type="button" onClick={() => setShowHistory(!showHistory)} style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.65rem 1rem", background: "transparent", border: "none", borderBottom: showHistory ? "1px solid var(--border)" : "none", cursor: "pointer", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <ArrowLeftRight size={13} style={{ color: "var(--text-secondary)" }} />
            <span style={{ fontWeight: 600, fontSize: "0.8rem", color: "var(--text-primary)" }}>Version History</span>
            {history.length > 0 && <span style={{ fontSize: "0.62rem", padding: "1px 6px", borderRadius: "4px", background: "rgba(168,85,247,0.12)", color: "#a855f7", fontWeight: 600 }}>{history.length} version{history.length !== 1 ? "s" : ""}</span>}
          </div>
          {showHistory ? <ChevronUp size={13} style={{ color: "var(--text-muted)" }} /> : <ChevronDown size={13} style={{ color: "var(--text-muted)" }} />}
        </button>
        {showHistory && <div style={{ padding: "1rem 1rem 0.75rem" }}><VersionHistoryPanel history={history} /></div>}
      </div>

      {/* Sku Master Change Banner */}
      {skuChangeStatus?.change_detected && (
        <div style={{ background: "rgba(168,85,247,0.07)", border: "1px solid rgba(168,85,247,0.35)", borderRadius: "12px", padding: "0.9rem 1rem" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <Bell size={16} style={{ color: "#a855f7", marginTop: 2, flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <strong style={{ fontSize: "0.83rem", color: "var(--text-primary)" }}>Hub SKU Master Sheet Changed</strong>
                {skuChangeStatus.change_history.length > 0 && <span style={{ fontSize: "0.62rem", padding: "1px 6px", borderRadius: "4px", background: "rgba(168,85,247,0.15)", color: "#a855f7", fontWeight: 700 }}>{skuChangeStatus.change_history[0].summary}</span>}
                {skuChangeStatus.change_history.length > 0 && <span style={{ fontSize: "0.63rem", color: "var(--text-muted)" }}>{relativeTime(skuChangeStatus.change_history[0].detected_at)}</span>}
              </div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", margin: "0 0 8px" }}>The Hub SKU Master configuration was updated. Email alert has been sent.</p>
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" onClick={() => { setShowSkuHistory(true); dismissSkuChanges(); }} style={{ fontSize: "0.72rem", padding: "4px 12px", background: "#a855f7", color: "#fff", border: "none", borderRadius: "6px", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                  <ArrowLeftRight size={11} /> View Sku Version History
                </button>
                <button type="button" className="btn btn-sm btn-ghost" style={{ fontSize: "0.72rem", padding: "4px 12px", height: "auto" }} onClick={dismissSkuChanges}>Dismiss</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Hub SKU Master Sheet Table */}
      <div className="card" style={{ borderRadius: "12px", padding: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", flexDirection: "column", padding: "0.65rem 1rem", borderBottom: "1px solid var(--border)", background: "rgba(255,255,255,0.02)", gap: 6 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Database size={14} style={{ color: "#a855f7" }} />
              <span style={{ fontWeight: 600, fontSize: "0.8rem", color: "var(--text-primary)" }}>Hub SKU Master Sheet</span>
              {skuData && <span style={{ fontSize: "0.62rem", padding: "1px 6px", borderRadius: "4px", background: "rgba(168,85,247,0.12)", color: "#a855f7", fontWeight: 600 }}>{skuData.row_count} rows</span>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {canWrite && (
                <button
                  type="button"
                  onClick={() => setShowAddSku(true)}
                  style={{
                    fontSize: "0.78rem", padding: "6px 14px", height: "auto",
                    display: "flex", alignItems: "center", gap: 5,
                    background: "linear-gradient(135deg, rgba(168,85,247,0.15), rgba(99,102,241,0.12))",
                    border: "1px solid rgba(168,85,247,0.35)", borderRadius: "8px",
                    color: "#a855f7", fontWeight: 600, cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = "linear-gradient(135deg, rgba(168,85,247,0.25), rgba(99,102,241,0.2))";
                    e.currentTarget.style.borderColor = "rgba(168,85,247,0.55)";
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = "linear-gradient(135deg, rgba(168,85,247,0.15), rgba(99,102,241,0.12))";
                    e.currentTarget.style.borderColor = "rgba(168,85,247,0.35)";
                  }}
                >
                  <Plus size={12} />
                  Add SKU
                </button>
              )}

              <button type="button" className="btn btn-sm btn-ghost" style={{ fontSize: "0.68rem", padding: "4px 10px", height: "auto", display: "flex", alignItems: "center", gap: 3 }} onClick={() => fetchSkuMaster(true)} disabled={loadingSku}>
                <RefreshCw size={10} className={loadingSku ? "animate-spin" : ""} /> {loadingSku ? "Fetching..." : "Refresh Live"}
              </button>
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.64rem", color: "var(--text-muted)", flexWrap: "wrap", gap: 8, borderTop: "1px solid rgba(255,255,255,0.03)", paddingTop: "6px" }}>
            {skuLastUpdate && skuLastUpdate.ts ? (
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <Clock size={10} />
                Last updated by : <strong style={{ color: "var(--text-secondary)" }}>{skuLastUpdate.user_id}</strong> at {formatIST(skuLastUpdate.ts)}
              </span>
            ) : (
              <span />
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              {skuChangeStatus?.last_checked_at && <span style={{ fontSize: "0.6rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 3 }}><Clock size={9} /> Checked {relativeTime(skuChangeStatus.last_checked_at)}</span>}
              {skuData?.cache_last_updated && <span style={{ fontSize: "0.6rem", color: "var(--text-muted)" }}>Cached: {formatIST(skuData.cache_last_updated)}</span>}
            </div>
          </div>
        </div>
        {loadingSku && !skuData ? (
          <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.78rem" }}><RefreshCw size={13} className="animate-spin inline mr-2" />Loading Hub SKU Master...</div>
        ) : skuData && skuData.rows.length > 0 ? (
          <div style={{ overflowX: "auto", maxHeight: "210px", overflowY: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.71rem" }}>
              <thead><tr style={{ background: "rgba(255,255,255,0.04)", borderBottom: "1px solid var(--border)", position: "sticky", top: 0 }}>{skuData.headers.map(h => <th key={h} style={{ padding: "0.38rem 0.75rem", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)", whiteSpace: "nowrap", textTransform: "uppercase", letterSpacing: "0.04em", fontSize: "0.62rem" }}>{h}</th>)}</tr></thead>
              <tbody>{skuData.rows.map((row, i) => <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>{skuData.headers.map(h => <td key={h} style={{ padding: "0.33rem 0.75rem", color: "var(--text-primary)", whiteSpace: "nowrap" }}>{String(row[h] ?? "")}</td>)}</tr>)}</tbody>
            </table>
          </div>
        ) : (
          <div style={{ padding: "1.25rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.78rem" }}>No SKU Master rows. Click Refresh Live to fetch from sheet.</div>
        )}
      </div>

      {/* Hub SKU Master Version History */}
      <div className="card" style={{ borderRadius: "12px", padding: 0, overflow: "hidden" }}>
        <button type="button" onClick={() => setShowSkuHistory(!showSkuHistory)} style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.65rem 1rem", background: "transparent", border: "none", borderBottom: showSkuHistory ? "1px solid var(--border)" : "none", cursor: "pointer", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <ArrowLeftRight size={13} style={{ color: "var(--text-secondary)" }} />
            <span style={{ fontWeight: 600, fontSize: "0.8rem", color: "var(--text-primary)" }}>Hub SKU Master Version History</span>
            {skuChangeStatus && skuChangeStatus.change_history.length > 0 && <span style={{ fontSize: "0.62rem", padding: "1px 6px", borderRadius: "4px", background: "rgba(168,85,247,0.12)", color: "#a855f7", fontWeight: 600 }}>{skuChangeStatus.change_history.length} version{skuChangeStatus.change_history.length !== 1 ? "s" : ""}</span>}
          </div>
          {showSkuHistory ? <ChevronUp size={13} style={{ color: "var(--text-muted)" }} /> : <ChevronDown size={13} style={{ color: "var(--text-muted)" }} />}
        </button>
        {showSkuHistory && skuChangeStatus && <div style={{ padding: "1rem 1rem 0.75rem" }}><SkuVersionHistoryPanel history={skuChangeStatus.change_history} /></div>}
      </div>

      {msg.text && (
        <div className="flex items-start gap-3 p-4 rounded-xl border text-sm" style={{ background: msg.type === "success" ? "rgba(16,185,129,0.06)" : msg.type === "warning" ? "rgba(234,179,8,0.06)" : "rgba(239,68,68,0.06)", borderColor: msg.type === "success" ? "rgba(16,185,129,0.3)" : msg.type === "warning" ? "rgba(234,179,8,0.3)" : "rgba(239,68,68,0.3)", color: "var(--text-primary)" }}>
          {msg.type === "success" ? <CheckCircle2 className="w-5 h-5 shrink-0" style={{ color: "#10b981" }} /> : msg.type === "warning" ? <AlertTriangle className="w-5 h-5 shrink-0" style={{ color: "#eab308" }} /> : <XCircle className="w-5 h-5 shrink-0" style={{ color: "#ef4444" }} />}
          <span style={{ fontSize: "0.8rem" }}>{msg.text}</span>
        </div>
      )}

      {/* Task 2: Hide Sync to P-H Master whole div */}
      {false && !syncSuccess && (
        <div className="card" style={{ borderRadius: "12px", padding: "1rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: showPreview && preview ? "1rem" : 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Eye size={13} style={{ color: "var(--blue)" }} />
              <span style={{ fontWeight: 600, fontSize: "0.8rem", color: "var(--text-primary)" }}>Sync to P-H Master</span>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => fetchPreview(false)} disabled={running} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                {running && !preview ? <RefreshCw size={11} className="animate-spin" /> : <Eye size={11} />} {running && !preview ? "Loading..." : "Preview Sync"}
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => fetchPreview(true)} disabled={running} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: "0.7rem" }}>
                <RefreshCw size={10} /> Bypass Cache
              </button>
              <button type="button" className="btn btn-primary btn-sm" onClick={handleConfirm} disabled={running || !preview || preview.rows_to_add.length === 0 || !canWrite} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                {running && preview ? <RefreshCw size={11} className="animate-spin" /> : <><Landmark size={11} /><ChevronRight size={11} /></>} {running && preview ? "Syncing..." : "Sync to P-H Master"}
              </button>
            </div>
          </div>
          {showPreview && preview && (
            <div>
              {preview.validation_errors.length > 0 && (
                <div style={{ background: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.25)", borderRadius: "8px", padding: "0.75rem", marginBottom: "0.75rem" }}>
                  <h4 style={{ fontSize: "0.76rem", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 5px", display: "flex", alignItems: "center", gap: 4 }}><XCircle size={12} style={{ color: "#ef4444" }} /> Validation Failures</h4>
                  <ul style={{ listStyle: "disc", paddingLeft: "1.25rem", fontSize: "0.71rem", color: "var(--text-secondary)", lineHeight: 1.7, margin: 0 }}>{preview.validation_errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
                </div>
              )}
              <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: "8px" }}>
                <div style={{ padding: "0.5rem 0.75rem", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)" }}>
                  <span style={{ fontSize: "0.76rem", fontWeight: 600, color: "var(--text-primary)" }}>Sync Mappings</span>
                  <div style={{ display: "flex", gap: 10, fontSize: "0.68rem", color: "var(--text-secondary)" }}>
                    <span><strong style={{ color: "var(--text-primary)" }}>{preview.total_to_insert}</strong> to sync</span>
                    <span>-</span><span><strong style={{ color: "var(--text-muted)" }}>{preview.duplicates_skipped}</strong> skipped</span>
                    {preview._elapsed_ms && <><span>-</span><span style={{ color: "var(--text-muted)" }}>{preview._elapsed_ms}ms</span></>}
                  </div>
                </div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.71rem" }}>
                  <thead><tr style={{ background: "rgba(255,255,255,0.03)", borderBottom: "1px solid var(--border)" }}>{["New Hub","Source Hub","Status","Rows Added","Skipped"].map(h => <th key={h} style={{ padding: "0.38rem 0.75rem", textAlign: (h==="Rows Added"||h==="Skipped") ? "right" : "left", fontWeight: 600, color: "var(--text-secondary)", whiteSpace: "nowrap", fontSize: "0.63rem", textTransform: "uppercase" }}>{h}</th>)}</tr></thead>
                  <tbody>{preview.mapping_report.map((rep, idx) => <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}><td style={{ padding: "0.33rem 0.75rem", fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap" }}>{rep.new_hub}</td><td style={{ padding: "0.33rem 0.75rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>{rep.source_hub}</td><td style={{ padding: "0.33rem 0.75rem" }}><span style={{ display: "inline-flex", padding: "1px 5px", borderRadius: "3px", fontSize: "0.6rem", fontWeight: 600, background: rep.status==="ok" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)", color: rep.status==="ok" ? "#10b981" : "#ef4444" }}>{rep.status==="ok" ? "Valid" : "Missing"}</span></td><td style={{ padding: "0.33rem 0.75rem", textAlign: "right", fontWeight: 600 }}>{rep.rows_inserted??0}</td><td style={{ padding: "0.33rem 0.75rem", textAlign: "right", color: "var(--text-muted)" }}>{rep.duplicates_skipped??0}</td></tr>)}</tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Task 2: Hide Sync successful div */}
      {false && syncSuccess && (
        <div className="card" style={{ borderRadius: "12px", padding: "1.5rem", textAlign: "center", border: "1px solid rgba(16,185,129,0.25)" }}>
          <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 40, height: 40, borderRadius: "50%", background: "rgba(16,185,129,0.1)", marginBottom: "0.6rem" }}>
            <CheckCircle2 size={18} style={{ color: "#10b981" }} />
          </div>
          <h3 style={{ fontWeight: 600, fontSize: "0.95rem", color: "var(--text-primary)", marginBottom: "0.3rem" }}>Sync Successful</h3>
          <p style={{ fontSize: "0.76rem", color: "var(--text-secondary)", maxWidth: 400, margin: "0 auto 1rem" }}>{syncedCount} product-hub configurations synced to P-H Master.</p>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => { setSyncSuccess(false); setPreview(null); setShowPreview(false); }}>New Sync Run</button>
        </div>
      )}
    </div>
  );
}
