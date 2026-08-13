"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import {
  CheckCircle2,
  Clock,
  Database,
  ExternalLink,
  FileSpreadsheet,
  RefreshCw,
  XCircle,
} from "lucide-react";

interface LastSyncInfo {
  started_at: string | null;
  status: string;
  full_name: string;
  email: string;
}

interface SheetMeta {
  key: string;
  label: string;
  url: string;
  group: string;
  has_gid: boolean;
  last_sync: LastSyncInfo | null;
}

interface TaskState {
  taskId: string;
  status: string;
  errorMessage?: string;
  sheetKey: string;
}

function formatIST(raw: string): string {
  if (!raw) return "—";
  try {
    return new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    }).format(new Date(raw));
  } catch {
    return raw;
  }
}

function SheetCard({
  sheet,
  isSyncing,
  task,
  onSync,
}: {
  sheet: SheetMeta;
  isSyncing: boolean;
  task?: TaskState;
  onSync: (key: string) => void;
}) {
  const lastSync = sheet.last_sync;
  const isPolling = task?.status === "pending" || task?.status === "processing" || task?.status === "queued";
  const isDone = task?.status === "completed";
  const isFailed = task?.status === "failed";

  return (
    <div className={`
      bg-white dark:bg-slate-900 border rounded-xl p-4 transition-all duration-200
      ${isSyncing
        ? "border-blue-300 dark:border-blue-600 shadow-md shadow-blue-100 dark:shadow-blue-950"
        : "border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md hover:border-slate-300 dark:hover:border-slate-700"
      }
    `}>
      <div className="flex items-center gap-4">
        <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center flex-shrink-0">
          <Database size={16} className="text-blue-600 dark:text-blue-400" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 leading-tight">
            {sheet.label}
          </p>
          {lastSync ? (
            <div className="flex items-center gap-1.5 mt-0.5 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
              <Clock size={11} className="flex-shrink-0" />
              <span>{formatIST(lastSync.started_at || "")}</span>
              <span className="text-slate-300 dark:text-slate-600">·</span>
              <span className="font-medium text-slate-700 dark:text-slate-300 max-w-[180px] truncate">
                {lastSync.email || lastSync.full_name}
              </span>
              <span className="text-slate-300 dark:text-slate-600">·</span>
              <span className={`font-semibold ${lastSync.status === "success" ? "text-emerald-600 dark:text-emerald-400" : "text-red-500 dark:text-red-400"}`}>
                {lastSync.status === "success" ? "✓ Synced" : "✗ Failed"}
              </span>
            </div>
          ) : (
            <p className="text-xs text-slate-400 dark:text-slate-600 italic mt-0.5">Never synced</p>
          )}
        </div>

        {sheet.url && (
          <a
            href={sheet.url}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden sm:inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-1.5 hover:bg-blue-100 dark:hover:bg-blue-900 transition-colors whitespace-nowrap"
          >
            <ExternalLink size={12} />
            Open Sheet
          </a>
        )}

        <button
          type="button"
          disabled={isSyncing}
          onClick={() => onSync(sheet.key)}
          className="inline-flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white transition-colors whitespace-nowrap shadow-sm"
        >
          {isSyncing ? (
            <span className="spinner" style={{ width: 11, height: 11, borderTopColor: "white" }} />
          ) : (
            <FileSpreadsheet size={12} />
          )}
          {isSyncing ? "Syncing…" : "Sync Now"}
        </button>
      </div>

      {(isPolling || isDone || isFailed) && (
        <div className="mt-3">
          {isPolling && (
            <div className="flex items-center gap-2 text-xs text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2">
              <span className="spinner" style={{ width: 11, height: 11, borderTopColor: "currentColor" }} />
              Queued — syncing in the background…
            </div>
          )}
          {isDone && (
            <div className="flex items-center gap-2 text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 rounded-lg px-3 py-2">
              <CheckCircle2 size={13} className="flex-shrink-0" />
              <span>
                Sync complete — saved to{" "}
                <code className="font-mono bg-emerald-100 dark:bg-emerald-900 px-1 rounded text-[11px]">base_sheet_baseline/</code>
              </span>
            </div>
          )}
          {isFailed && (
            <div className="flex items-start gap-2 text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
              <XCircle size={13} className="flex-shrink-0 mt-0.5" />
              <span>
                Sync failed: <span className="font-medium">{task?.errorMessage || "Unknown error"}</span>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function BaseSheetsSection() {
  const [sheets, setSheets] = useState<SheetMeta[]>([]);
  const [loadingSheets, setLoadingSheets] = useState(false);
  const [syncBusy, setSyncBusy] = useState<Record<string, boolean>>({});
  const [activeTasks, setActiveTasks] = useState<Record<string, TaskState>>({});
  const [sheetError, setSheetError] = useState("");
  const [activeGroup, setActiveGroup] = useState("");

  const groups = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const s of sheets) {
      if (s.group && !seen.has(s.group)) { seen.add(s.group); out.push(s.group); }
    }
    return out;
  }, [sheets]);

  useEffect(() => {
    if (groups.length > 0 && !activeGroup) setActiveGroup(groups[0]);
  }, [groups, activeGroup]);

  const visibleSheets = useMemo(
    () => sheets.filter((s) => s.group === activeGroup),
    [sheets, activeGroup]
  );

  const loadSheets = useCallback(async () => {
    setLoadingSheets(true);
    setSheetError("");
    try {
      const { data } = await api.get<SheetMeta[]>("/api/base-sheets/list");
      setSheets(data);
    } catch {
      setSheetError("Could not load base sheets. Check backend connectivity.");
    } finally {
      setLoadingSheets(false);
    }
  }, []);

  useEffect(() => { loadSheets(); }, [loadSheets]);

  useEffect(() => {
    const active = Object.entries(activeTasks).filter(
      ([, t]) => t.status === "pending" || t.status === "processing" || t.status === "queued"
    );
    if (active.length === 0) return;
    const iv = setInterval(async () => {
      for (const [key, task] of active) {
        try {
          const { data } = await api.get<{ status: string; error_message?: string }>(
            `/api/base-sheets/tasks/${task.taskId}`
          );
          if (data.status === "completed" || data.status === "failed") {
            setActiveTasks((p) => ({ ...p, [key]: { ...p[key], status: data.status, errorMessage: data.error_message } }));
            setSyncBusy((p) => ({ ...p, [task.sheetKey]: false }));
            loadSheets();
          }
        } catch { /* ignore */ }
      }
    }, 2000);
    return () => clearInterval(iv);
  }, [activeTasks, loadSheets]);

  const handleSync = async (sheetKey: string) => {
    setSyncBusy((p) => ({ ...p, [sheetKey]: true }));
    setSheetError("");
    setActiveTasks((p) => { const c = { ...p }; delete c[sheetKey]; return c; });
    try {
      const { data } = await api.post<{ status: string; task_id: string }>(`/api/base-sheets/${sheetKey}/sync`);
      setActiveTasks((p) => ({ ...p, [sheetKey]: { taskId: data.task_id, status: "pending", sheetKey } }));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setSheetError(err?.response?.data?.detail || `Failed to queue sync for: ${sheetKey}`);
      setSyncBusy((p) => ({ ...p, [sheetKey]: false }));
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div className="card" style={{ padding: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--border)", paddingBottom: "1rem", marginBottom: "1rem" }}>
          <div>
            <h4 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700, color: "var(--text-primary)" }}>Base Sheet Sync</h4>
            <div className="text-xs text-muted mt-1">Sync base plan templates and master data layouts to Parquet on Google Drive.</div>
          </div>
          <button
            type="button"
            onClick={loadSheets}
            disabled={loadingSheets}
            className="btn btn-secondary btn-sm"
          >
            <RefreshCw size={13} className={loadingSheets ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <p className="text-xs text-muted">
            Sync configured worksheets into dated Parquet files (<code className="font-mono" style={{ fontSize: "0.72rem" }}>base_sheet_baseline/</code>).
          </p>
        </div>

        {sheetError && (
          <div className="alert alert-danger text-sm mb-4">{sheetError}</div>
        )}

        {/* Group tabs */}
        {groups.length > 1 && (
          <div style={{ display: "flex", gap: "0.25rem", padding: "4px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: "8px", marginBottom: "1.25rem", width: "fit-content" }}>
            {groups.map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setActiveGroup(g)}
                style={{
                  fontSize: "0.78rem", padding: "5px 12px", borderRadius: "6px",
                  border: "none", cursor: "pointer", fontWeight: 500,
                  background: activeGroup === g ? "var(--bg-hover)" : "transparent",
                  color: activeGroup === g ? "var(--text-primary)" : "var(--text-secondary)",
                  transition: "all 0.15s"
                }}
              >
                {g}
                <span style={{
                  marginLeft: "0.4rem", fontSize: "0.62rem", padding: "1px 5px", borderRadius: "8px",
                  background: activeGroup === g ? "rgba(59,130,246,0.15)" : "var(--border)",
                  color: activeGroup === g ? "var(--blue)" : "var(--text-muted)",
                  fontWeight: 600
                }}>
                  {sheets.filter((s) => s.group === g).length}
                </span>
              </button>
            ))}
          </div>
        )}

        {loadingSheets && sheets.length === 0 ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl bg-slate-100 dark:bg-slate-800 animate-pulse" />)}
          </div>
        ) : (
          <div className="space-y-3">
            {visibleSheets.map((sheet) => (
              <SheetCard
                key={sheet.key}
                sheet={sheet}
                isSyncing={!!syncBusy[sheet.key]}
                task={activeTasks[sheet.key]}
                onSync={handleSync}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
