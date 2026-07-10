"use client";

import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Landmark,
  Eye,
  Database,
  GitDiff,
  Bell,
  ChevronRight,
} from "lucide-react";

interface FFRow {
  [key: string]: string | number;
}

interface FFInputData {
  rows: FFRow[];
  headers: string[];
  row_count: number;
  content_hash: string;
  cache_last_updated: string | null;
  _elapsed_ms?: number;
}

interface PreviewData {
  success: boolean;
  validation_errors: string[];
  rows_to_add: Record<string, unknown>[];
  ph_headers: string[];
  duplicates_skipped: number;
  mapping_report: Array<{
    new_hub: string;
    source_hub: string;
    status: string;
    rows_inserted?: number;
    duplicates_skipped?: number;
    message?: string;
  }>;
  total_to_insert: number;
  cache_last_updated?: string | null;
  _elapsed_ms?: number;
}

const formatIST = (raw: string | null | undefined): string => {
  if (!raw) return "Never Fetched";
  try {
    return (
      new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).format(new Date(raw)) + " IST"
    );
  } catch {
    return raw;
  }
};

export default function HubLaunchTab() {
  const { canWrite } = useAuth();
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [step, setStep] = useState<"idle" | "preview" | "success">("idle");
  const [syncedCount, setSyncedCount] = useState(0);

  // FF Input sheet data state
  const [ffData, setFfData] = useState<FFInputData | null>(null);
  const [loadingFf, setLoadingFf] = useState(false);
  const [prevHash, setPrevHash] = useState<string | null>(null);
  const [changeRows, setChangeRows] = useState<FFRow[]>([]);
  const [hasChanges, setHasChanges] = useState(false);
  const [showChangeDiff, setShowChangeDiff] = useState(false);
  const prevRowsRef = useRef<FFRow[]>([]);

  useEffect(() => {
    fetchFFInput(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchFFInput = async (bypass: boolean) => {
    setLoadingFf(true);
    const t0 = performance.now();
    try {
      const { data } = await api.get<FFInputData>(
        `/api/new-product-launch/sync-new-hub/ff-input?bypass_cache=${bypass}`
      );
      const elapsed = Math.round(performance.now() - t0);
      console.info(`[HubLaunchTab] FF Input: ${data.row_count} rows in ${elapsed}ms`);

      if (prevHash && data.content_hash && prevHash !== data.content_hash) {
        const prevSet = new Set(prevRowsRef.current.map((r) => JSON.stringify(r)));
        const added = data.rows.filter((r) => !prevSet.has(JSON.stringify(r)));
        setChangeRows(added);
        setHasChanges(true);
        setShowChangeDiff(true);
      }

      prevRowsRef.current = data.rows;
      setPrevHash(data.content_hash);
      setFfData(data);
    } catch (e: unknown) {
      console.error("[HubLaunchTab] FF Input fetch failed:", e);
    } finally {
      setLoadingFf(false);
    }
  };

  const fetchPreview = async (bypassCache: boolean = false) => {
    setRunning(true);
    setMsg({ text: "", type: "" });
    setPreview(null);
    const t0 = performance.now();
    try {
      const { data } = await api.get<PreviewData>(
        `/api/new-product-launch/sync-new-hub/preview?bypass_cache=${bypassCache}`
      );
      const elapsed = Math.round(performance.now() - t0);
      setPreview(data);
      setStep("preview");
      if (data.validation_errors && data.validation_errors.length > 0) {
        setMsg({
          text: `Found ${data.validation_errors.length} Hub Mapping issue(s). Resolve in Google Sheets and refresh.`,
          type: "warning",
        });
      } else {
        setMsg({
          text: `Preview loaded: ${data.total_to_insert} rows to sync, ${data.duplicates_skipped} duplicates skipped · ${elapsed}ms`,
          type: "success",
        });
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Failed to load sync preview.", type: "danger" });
    } finally {
      setRunning(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setRunning(true);
    setMsg({ text: "", type: "" });
    const t0 = performance.now();
    try {
      const { data } = await api.post("/api/new-product-launch/sync-new-hub/confirm", {
        rows_to_add: preview.rows_to_add,
        ph_headers: preview.ph_headers,
      });
      const elapsed = Math.round(performance.now() - t0);
      setSyncedCount(data.rows_inserted);
      setStep("success");
      setMsg({ text: `${data.detail || "New Hub settings synced."} · ${elapsed}ms`, type: "success" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Sync confirmation failed", type: "danger" });
    } finally {
      setRunning(false);
    }
  };

  const resetFlow = () => {
    setPreview(null);
    setStep("idle");
    setMsg({ text: "", type: "" });
  };

  const dismissChanges = () => {
    setHasChanges(false);
    setShowChangeDiff(false);
    setChangeRows([]);
  };

  return (
    <div className="w-full max-w-5xl space-y-4">

      {/* MASTERS UPDATE ALERT */}
      <div
        className="flex items-start gap-3 p-4 rounded-xl border"
        style={{ background: "rgba(234,179,8,0.06)", borderColor: "rgba(234,179,8,0.3)" }}
      >
        <Bell className="w-5 h-5 shrink-0 mt-0.5" style={{ color: "#eab308" }} />
        <div className="text-sm">
          <strong style={{ display: "block", marginBottom: "0.15rem", color: "var(--text-primary)" }}>
            Update Masters Before Syncing
          </strong>
          <span style={{ color: "var(--text-secondary)", fontSize: "0.8rem" }}>
            Ensure <strong>Hub Mapping</strong>, <strong>P-H Master</strong>, and <strong>FF Input</strong> tabs
            are up-to-date. Stale master data can cause mismatched configurations.
          </span>
        </div>
      </div>

      {/* FF INPUT LIVE TABLE */}
      <div className="card" style={{ borderRadius: "12px", padding: 0, overflow: "hidden" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "0.75rem 1rem",
            borderBottom: "1px solid var(--border)",
            background: "rgba(255,255,255,0.02)",
          }}
        >
          <div className="flex items-center gap-2">
            <Database size={15} style={{ color: "var(--blue)" }} />
            <span style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--text-primary)" }}>
              FF Input Sheet (Live)
            </span>
            {ffData && (
              <span style={{
                fontSize: "0.65rem",
                padding: "1px 6px",
                borderRadius: "4px",
                background: "rgba(59,130,246,0.1)",
                color: "var(--blue)",
                fontWeight: 600,
              }}>
                {ffData.row_count} rows
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {ffData?.cache_last_updated && (
              <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>
                Cached: {formatIST(ffData.cache_last_updated)}
              </span>
            )}
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              style={{ fontSize: "0.7rem", padding: "2px 8px", height: "auto", display: "flex", alignItems: "center", gap: 4 }}
              onClick={() => fetchFFInput(true)}
              disabled={loadingFf}
            >
              <RefreshCw size={12} className={loadingFf ? "animate-spin" : ""} />
              {loadingFf ? "Fetching..." : "Refresh Live"}
            </button>
          </div>
        </div>

        {loadingFf && !ffData ? (
          <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.8rem" }}>
            <RefreshCw size={16} className="animate-spin inline mr-2" />
            Loading FF Input data…
          </div>
        ) : ffData && ffData.rows.length > 0 ? (
          <div style={{ overflowX: "auto", maxHeight: "260px", overflowY: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.72rem" }}>
              <thead>
                <tr style={{
                  background: "rgba(255,255,255,0.04)",
                  borderBottom: "1px solid var(--border)",
                  position: "sticky",
                  top: 0,
                }}>
                  {ffData.headers.map((h) => (
                    <th key={h} style={{
                      padding: "0.45rem 0.75rem",
                      textAlign: "left",
                      fontWeight: 600,
                      color: "var(--text-secondary)",
                      whiteSpace: "nowrap",
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      fontSize: "0.65rem",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ffData.rows.map((row, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    {ffData.headers.map((h) => (
                      <td key={h} style={{
                        padding: "0.4rem 0.75rem",
                        color: "var(--text-primary)",
                        whiteSpace: "nowrap",
                      }}>{String(row[h] ?? "")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.8rem" }}>
            No FF Input rows found. Click &quot;Refresh Live&quot; to fetch from sheet.
          </div>
        )}
      </div>

      {/* CHANGE DETECTION BANNER */}
      {hasChanges && (
        <div style={{
          background: "rgba(168,85,247,0.06)",
          border: "1px solid rgba(168,85,247,0.3)",
          borderRadius: "12px",
          padding: "1rem",
        }}>
          <div className="flex items-start gap-3">
            <GitDiff size={18} className="shrink-0 mt-0.5" style={{ color: "#a855f7" }} />
            <div style={{ flex: 1 }}>
              <div style={{
                fontWeight: 600,
                fontSize: "0.82rem",
                color: "var(--text-primary)",
                marginBottom: "0.25rem",
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}>
                Changes Detected in FF Input Sheet
                <span style={{
                  fontSize: "0.62rem",
                  padding: "1px 6px",
                  borderRadius: "4px",
                  background: "rgba(168,85,247,0.15)",
                  color: "#a855f7",
                }}>
                  {changeRows.length} new/changed row{changeRows.length !== 1 ? "s" : ""}
                </span>
              </div>
              <p style={{
                fontSize: "0.75rem",
                color: "var(--text-secondary)",
                marginBottom: showChangeDiff ? "0.75rem" : "0.5rem",
              }}>
                The FF Input sheet was updated since your last fetch. Review changes and ensure Master sheets are updated.
              </p>

              {showChangeDiff && changeRows.length > 0 && (
                <div style={{ marginBottom: "0.75rem", overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.7rem" }}>
                    <thead>
                      <tr style={{ background: "rgba(168,85,247,0.08)", borderBottom: "1px solid rgba(168,85,247,0.2)" }}>
                        {Object.keys(changeRows[0]).map((h) => (
                          <th key={h} style={{
                            padding: "0.3rem 0.6rem",
                            textAlign: "left",
                            fontWeight: 600,
                            color: "#a855f7",
                            whiteSpace: "nowrap",
                            fontSize: "0.62rem",
                            textTransform: "uppercase",
                          }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {changeRows.map((row, i) => (
                        <tr key={i} style={{ background: "rgba(168,85,247,0.04)", borderBottom: "1px solid rgba(168,85,247,0.1)" }}>
                          {Object.values(row).map((v, j) => (
                            <td key={j} style={{ padding: "0.3rem 0.6rem", color: "var(--text-primary)", whiteSpace: "nowrap" }}>
                              {String(v ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  style={{
                    fontSize: "0.72rem", padding: "4px 12px", height: "auto",
                    background: "#a855f7", color: "#fff", border: "none",
                    borderRadius: "6px", cursor: "pointer",
                  }}
                  onClick={() => setShowChangeDiff(!showChangeDiff)}
                >
                  {showChangeDiff ? "Hide Changes" : "Show Changes"}
                </button>
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  style={{ fontSize: "0.72rem", padding: "4px 12px", height: "auto" }}
                  onClick={dismissChanges}
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* STATUS MESSAGE */}
      {msg.text && (
        <div
          className="flex items-start gap-3 p-4 rounded-xl border text-sm"
          style={{
            background: msg.type === "success" ? "rgba(16,185,129,0.06)" : msg.type === "warning" ? "rgba(234,179,8,0.06)" : "rgba(239,68,68,0.06)",
            borderColor: msg.type === "success" ? "rgba(16,185,129,0.3)" : msg.type === "warning" ? "rgba(234,179,8,0.3)" : "rgba(239,68,68,0.3)",
            color: "var(--text-primary)",
          }}
        >
          {msg.type === "success" ? (
            <CheckCircle2 className="w-5 h-5 shrink-0" style={{ color: "#10b981" }} />
          ) : msg.type === "warning" ? (
            <AlertTriangle className="w-5 h-5 shrink-0" style={{ color: "#eab308" }} />
          ) : (
            <XCircle className="w-5 h-5 shrink-0" style={{ color: "#ef4444" }} />
          )}
          <span style={{ fontSize: "0.82rem" }}>{msg.text}</span>
        </div>
      )}

      {/* STEP 1: Idle */}
      {step === "idle" && (
        <div className="card" style={{ borderRadius: "12px", padding: "1.5rem", textAlign: "center" }}>
          <div style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 44, height: 44, borderRadius: "50%",
            background: "rgba(59,130,246,0.1)", marginBottom: "0.75rem",
          }}>
            <Landmark size={20} style={{ color: "var(--blue)" }} />
          </div>
          <h3 style={{ fontWeight: 600, fontSize: "1rem", color: "var(--text-primary)", marginBottom: "0.5rem" }}>
            Preview Launch Parameters
          </h3>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", maxWidth: 480, margin: "0 auto 1.25rem" }}>
            Loads pending hub settings from FF Input, runs validations, and shows skipped/new records before merging into P-H Master.
          </p>
          <div className="flex items-center justify-center gap-3 flex-wrap">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => fetchPreview(false)}
              disabled={running}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              {running ? <RefreshCw size={13} className="animate-spin" /> : <Eye size={13} />}
              {running ? "Reading..." : "Fetch & Preview Sync Mappings"}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => fetchPreview(true)}
              disabled={running}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              <RefreshCw size={13} className={running ? "animate-spin" : ""} />
              {running ? "Fetching Live..." : "Fetch Live (Bypass Cache)"}
            </button>
          </div>
        </div>
      )}

      {/* STEP 2: Preview Results */}
      {step === "preview" && preview && (
        <div className="space-y-4">
          {preview.validation_errors.length > 0 && (
            <div style={{
              background: "rgba(239,68,68,0.06)",
              border: "1px solid rgba(239,68,68,0.25)",
              borderRadius: "10px",
              padding: "1rem",
            }}>
              <h4 className="flex items-center gap-2" style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                <XCircle size={14} style={{ color: "#ef4444" }} />
                Validation Failures in Hub Mapping
              </h4>
              <ul style={{ listStyle: "disc", paddingLeft: "1.25rem", fontSize: "0.75rem", color: "var(--text-secondary)", lineHeight: 1.7 }}>
                {preview.validation_errors.map((err, i) => <li key={i}>{err}</li>)}
              </ul>
            </div>
          )}

          <div className="card" style={{ borderRadius: "12px", overflow: "hidden", padding: 0 }}>
            <div style={{
              padding: "0.75rem 1rem",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              background: "rgba(255,255,255,0.02)",
            }}>
              <span style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--text-primary)" }}>
                Launch Configuration Sync Report
              </span>
              <div className="flex items-center gap-3" style={{ fontSize: "0.72rem", color: "var(--text-secondary)" }}>
                <span><strong style={{ color: "var(--text-primary)" }}>{preview.total_to_insert}</strong> to sync</span>
                <span>·</span>
                <span><strong style={{ color: "var(--text-muted)" }}>{preview.duplicates_skipped}</strong> skipped</span>
                {preview._elapsed_ms && <><span>·</span><span style={{ color: "var(--text-muted)" }}>{preview._elapsed_ms}ms</span></>}
              </div>
            </div>
            <div style={{ overflowX: "auto", maxHeight: "280px", overflowY: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.73rem" }}>
                <thead>
                  <tr style={{ background: "rgba(255,255,255,0.04)", borderBottom: "1px solid var(--border)", position: "sticky", top: 0 }}>
                    {["New Hub", "Source Hub", "Status", "Rows Added", "Skipped"].map((h) => (
                      <th key={h} style={{
                        padding: "0.45rem 1rem",
                        textAlign: h === "Rows Added" || h === "Skipped" ? "right" : "left",
                        fontWeight: 600,
                        color: "var(--text-secondary)",
                        whiteSpace: "nowrap",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.mapping_report.map((rep, idx) => (
                    <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "0.4rem 1rem", fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap" }}>{rep.new_hub}</td>
                      <td style={{ padding: "0.4rem 1rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>{rep.source_hub}</td>
                      <td style={{ padding: "0.4rem 1rem", whiteSpace: "nowrap" }}>
                        <span style={{
                          display: "inline-flex", alignItems: "center",
                          padding: "1px 7px", borderRadius: "4px",
                          fontSize: "0.65rem", fontWeight: 600,
                          background: rep.status === "ok" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
                          color: rep.status === "ok" ? "#10b981" : "#ef4444",
                        }}>
                          {rep.status === "ok" ? "Valid" : "Missing Row"}
                        </span>
                      </td>
                      <td style={{ padding: "0.4rem 1rem", textAlign: "right", fontWeight: 600, color: "var(--text-primary)" }}>{rep.rows_inserted ?? 0}</td>
                      <td style={{ padding: "0.4rem 1rem", textAlign: "right", color: "var(--text-muted)" }}>{rep.duplicates_skipped ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <button type="button" className="btn btn-secondary btn-sm" onClick={resetFlow}>
              Reset
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleConfirm}
              disabled={running || preview.rows_to_add.length === 0 || !canWrite}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              {running ? (
                <RefreshCw size={13} className="animate-spin" />
              ) : (
                <><Landmark size={13} /><ChevronRight size={13} /></>
              )}
              {running ? "Syncing to P-H Master..." : "Confirm & Sync to P-H Master"}
            </button>
          </div>
        </div>
      )}

      {/* STEP 3: Success */}
      {step === "success" && (
        <div className="card" style={{
          borderRadius: "12px", padding: "2rem", textAlign: "center",
          border: "1px solid rgba(16,185,129,0.25)",
        }}>
          <div style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 44, height: 44, borderRadius: "50%",
            background: "rgba(16,185,129,0.1)", marginBottom: "0.75rem",
          }}>
            <CheckCircle2 size={20} style={{ color: "#10b981" }} />
          </div>
          <h3 style={{ fontWeight: 600, fontSize: "1rem", color: "var(--text-primary)", marginBottom: "0.4rem" }}>
            Sync Successful
          </h3>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", maxWidth: 440, margin: "0 auto 1.25rem" }}>
            Successfully synced <strong style={{ color: "var(--text-primary)" }}>{syncedCount}</strong> product-hub
            forecast configurations into the P-H Master table.
          </p>
          <button type="button" className="btn btn-primary btn-sm" onClick={resetFlow}>
            Start New Run
          </button>
        </div>
      )}
    </div>
  );
}
