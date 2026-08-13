"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import api from "@/lib/api";
import {
  RefreshCw,
  CheckCircle2,
  FileSpreadsheet,
  XCircle,
  ExternalLink,
  Clock,
  AlertCircle,
  Database,
} from "lucide-react";

/* ── Types ─────────────────────────────────────────────────────────────────── */

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

/* ── Helpers ───────────────────────────────────────────────────────────────── */

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

/* ── Sheet Row Card ─────────────────────────────────────────────────────────── */

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
      {/* Main row */}
      <div className="flex items-center gap-4">

        {/* Icon badge */}
        <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center flex-shrink-0">
          <Database size={16} className="text-blue-600 dark:text-blue-400" />
        </div>

        {/* Sheet name + last sync */}
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

        {/* Open sheet link */}
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

        {/* Sync button */}
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

      {/* Status banner */}
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
                Sync failed:{" "}
                <span className="font-medium">{task?.errorMessage || "Unknown error — check backend logs."}</span>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────────────────────── */

export default function BaseSheetsPage() {
  const [sheets, setSheets] = useState<SheetMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncBusy, setSyncBusy] = useState<Record<string, boolean>>({});
  const [activeTasks, setActiveTasks] = useState<Record<string, TaskState>>({});
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<string>("");

  /* ── Derive tab names from data ──────────────────────────────────────────── */
  const tabs = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const s of sheets) {
      if (s.group && !seen.has(s.group)) {
        seen.add(s.group);
        out.push(s.group);
      }
    }
    return out;
  }, [sheets]);

  // Set first tab when data loads
  useEffect(() => {
    if (tabs.length > 0 && !activeTab) setActiveTab(tabs[0]);
  }, [tabs, activeTab]);

  const visibleSheets = useMemo(
    () => sheets.filter((s) => s.group === activeTab),
    [sheets, activeTab]
  );

  /* ── Load sheets ─────────────────────────────────────────────────────────── */
  const loadSheets = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await api.get<SheetMeta[]>("/api/base-sheets/list");
      setSheets(data);
    } catch {
      setError("Could not load base sheets. Check backend connectivity.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSheets(); }, [loadSheets]);

  /* ── Task polling ─────────────────────────────────────────────────────────── */
  useEffect(() => {
    const active = Object.entries(activeTasks).filter(
      ([, t]) => t.status === "pending" || t.status === "processing" || t.status === "queued"
    );
    if (active.length === 0) return;

    const interval = setInterval(async () => {
      for (const [key, task] of active) {
        try {
          const { data } = await api.get<{ status: string; error_message?: string }>(
            `/api/base-sheets/tasks/${task.taskId}`
          );
          if (data.status === "completed" || data.status === "failed") {
            setActiveTasks((prev) => ({
              ...prev,
              [key]: { ...prev[key], status: data.status, errorMessage: data.error_message },
            }));
            setSyncBusy((prev) => ({ ...prev, [task.sheetKey]: false }));
            loadSheets();
          }
        } catch { /* ignore transient polling errors */ }
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [activeTasks, loadSheets]);

  /* ── Sync handler ─────────────────────────────────────────────────────────── */
  const handleSync = async (sheetKey: string) => {
    setSyncBusy((prev) => ({ ...prev, [sheetKey]: true }));
    setError("");
    setActiveTasks((prev) => { const c = { ...prev }; delete c[sheetKey]; return c; });

    try {
      const { data } = await api.post<{ status: string; task_id: string }>(
        `/api/base-sheets/${sheetKey}/sync`
      );
      // Normalize to "pending" so the polling filter always picks it up
      setActiveTasks((prev) => ({
        ...prev,
        [sheetKey]: { taskId: data.task_id, status: "pending", sheetKey },
      }));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err?.response?.data?.detail || `Failed to queue sync for: ${sheetKey}`);
      setSyncBusy((prev) => ({ ...prev, [sheetKey]: false }));
    }
  };

  /* ── Render ──────────────────────────────────────────────────────────────── */
  return (
    <AppShell
      title="Base Sheets"
      subtitle="Sync Google Sheets to Google Drive as parquet files"
      actions={
        <button
          type="button"
          className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          onClick={loadSheets}
          disabled={loading}
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      }
    >
      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3 mb-5">
          <AlertCircle size={15} className="flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && sheets.length === 0 ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-16 rounded-xl bg-slate-100 dark:bg-slate-800 animate-pulse"
            />
          ))}
        </div>
      ) : sheets.length === 0 ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center py-16 text-center border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-2xl">
          <Database size={36} className="text-slate-300 dark:text-slate-600 mb-3" />
          <p className="font-medium text-slate-500 dark:text-slate-400">No base sheets configured</p>
          <p className="text-xs text-slate-400 dark:text-slate-600 mt-1">
            Edit <code className="font-mono">features/base_sheets/registry.py</code> to add sheets
          </p>
        </div>
      ) : (
        <>
          {/* Tab bar */}
          <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl mb-5 w-fit">
            {tabs.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={`
                  px-4 py-2 text-sm font-medium rounded-lg transition-all duration-150
                  ${activeTab === tab
                    ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm"
                    : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                  }
                `}
              >
                {tab}
                <span className={`
                  ml-2 text-[11px] font-semibold px-1.5 py-0.5 rounded-full
                  ${activeTab === tab
                    ? "bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300"
                    : "bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400"
                  }
                `}>
                  {sheets.filter((s) => s.group === tab).length}
                </span>
              </button>
            ))}
          </div>

          {/* Sheet cards for active tab */}
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
        </>
      )}
    </AppShell>
  );
}
