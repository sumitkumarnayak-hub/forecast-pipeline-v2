"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import SectionCard from "@/components/baseline/SectionCard";
import api from "@/lib/api";
import { useCachedQuery } from "@/hooks/useCachedQuery";
import { cacheInvalidate } from "@/lib/queryCache";
import { useAuth } from "@/hooks/useAuth";
import {
  CheckCircle2,
  Clock,
  Database,
  ExternalLink,
  FileSpreadsheet,
  RefreshCw,
  XCircle,
} from "lucide-react";

/* ════════════════════════════════════════════════════════════════════════════
   BASE SHEET SYNC — types & helpers
   ════════════════════════════════════════════════════════════════════════════ */

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

function BaseSheetsSection() {
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
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Sync Google Sheets to Google Drive as dated parquet files (<code className="font-mono text-xs">base_sheet_baseline/</code>).
        </p>
        <button
          type="button"
          onClick={loadSheets}
          disabled={loadingSheets}
          className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 hover:bg-slate-50 transition-colors"
        >
          <RefreshCw size={11} className={loadingSheets ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {sheetError && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-4">{sheetError}</div>
      )}

      {/* Group tabs */}
      {groups.length > 1 && (
        <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl mb-4 w-fit">
          {groups.map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setActiveGroup(g)}
              className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-all
                ${activeGroup === g
                  ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm"
                  : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                }`}
            >
              {g}
              <span className={`ml-1.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-full
                ${activeGroup === g ? "bg-blue-100 text-blue-700" : "bg-slate-200 text-slate-500"}`}>
                {sheets.filter((s) => s.group === g).length}
              </span>
            </button>
          ))}
        </div>
      )}

      {loadingSheets && sheets.length === 0 ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-xl bg-slate-100 animate-pulse" />)}
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
  );
}

/* ════════════════════════════════════════════════════════════════════════════
   CONFIGURE PARAMETERS — main content
   ════════════════════════════════════════════════════════════════════════════ */


function ConfigureContent() {
  const { readOnly } = useAuth();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // ── Params tab state ─────────────────────────────────────────────────────
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [dpStatus, setDpStatus] = useState<{
    worksheet: string;
    label: string;
    group: string;
    url: string;
    status: string;
    last_updated: string | null;
    last_sync: { started_at: string | null; status: string; full_name: string; email: string } | null;
  }[]>([]);
  const [masterSyncBusy, setMasterSyncBusy] = useState<Record<string, boolean>>({});
  const [masterSyncMessages, setMasterSyncMessages] = useState<Record<string, { text: string; type: "success" | "danger" }>>({});
  const [activeMasterGroup, setActiveMasterGroup] = useState<string>("");

  const masterGroups = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const s of dpStatus) {
      if (s.group && !seen.has(s.group)) {
        seen.add(s.group);
        out.push(s.group);
      }
    }
    return out;
  }, [dpStatus]);

  useEffect(() => {
    if (masterGroups.length > 0 && !activeMasterGroup) {
      setActiveMasterGroup(masterGroups[0]);
    }
  }, [masterGroups, activeMasterGroup]);

  const visibleMasterStatus = useMemo(
    () => dpStatus.filter((s) => s.group === activeMasterGroup),
    [dpStatus, activeMasterGroup]
  );

  const handleSyncMaster = async (worksheetName: string) => {
    setMasterSyncBusy((prev) => ({ ...prev, [worksheetName]: true }));
    setMasterSyncMessages((prev) => {
      const copy = { ...prev };
      delete copy[worksheetName];
      return copy;
    });
    try {
      await api.post(`/api/baseline/sync-dp-logics/${worksheetName}`);
      setMasterSyncMessages((prev) => ({
        ...prev,
        [worksheetName]: { text: "Sync complete — saved to Excel and sidecars refreshed", type: "success" },
      }));
      // Invalidate cache query
      cacheInvalidate("baseline:params");
      await load(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMasterSyncMessages((prev) => ({
        ...prev,
        [worksheetName]: { text: err?.response?.data?.detail || "Sync failed", type: "danger" },
      }));
    } finally {
      setMasterSyncBusy((prev) => ({ ...prev, [worksheetName]: false }));
    }
  };
  const [sheetUrl, setSheetUrl] = useState("");
  const [activeReady, setActiveReady] = useState(false);
  const [sidecars, setSidecars] = useState<Record<string, unknown>[]>([]);
  const [fetchingPrev, setFetchingPrev] = useState(false);
  const [prevPreview, setPrevPreview] = useState<Record<string, unknown> | null>(null);
  const [targetWeek, setTargetWeek] = useState(28);
  const [targetYear, setTargetYear] = useState(2026);

  const [flags, setFlags] = useState({
    use_clustering: true,
    remove_outliers: true,
    apply_hub_changes: true,
    use_availability: true,
    use_stf: true,
    use_percentile: true,
    weeks_back: 4,
    avail_threshold: 0.2,
  });

  const fetchParams = useCallback(async () => {
    const { data } = await api.get("/api/baseline/params");
    return data;
  }, []);

  const { data, loading, refreshing, refresh } = useCachedQuery(
    "baseline:params",
    fetchParams,
    { ttlMs: 180_000 },
  );

  useEffect(() => {
    if (!data) return;
    const p = data.params || {};
    setFlags({
      use_clustering: Boolean(p.use_clustering ?? true),
      remove_outliers: Boolean(p.remove_outliers ?? true),
      apply_hub_changes: Boolean(p.apply_hub_changes ?? true),
      use_availability: Boolean(p.use_availability ?? true),
      use_stf: Boolean(p.use_stf ?? true),
      use_percentile: Boolean(p.use_percentile ?? true),
      weeks_back: Number(p.weeks_back ?? 4),
      avail_threshold: Number(p.avail_threshold ?? 0.2),
    });
    setDpStatus(data.dp_worksheets_status || []);
    setActiveReady(Boolean(data.active_dataset_ready));
    setSheetUrl(data.dp_logics_sheet_url || "");
    setTargetWeek(Number(p.target_week) || 28);
    setTargetYear(Number(p.target_year) || 2026);
  }, [data]);

  const load = useCallback(
    (force = true) => {
      if (force) cacheInvalidate("baseline:params");
      return refresh(force);
    },
    [refresh],
  );

  const saveParams = async () => {
    setSaving(true);
    setMsg({ text: "", type: "" });
    try {
      await api.post("/api/baseline/params", flags);
      setMsg({ text: "Parameters saved to Google Sheet", type: "success" });
      cacheInvalidate("baseline:params");
      await load(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Save failed", type: "danger" });
    } finally {
      setSaving(false);
    }
  };

  const syncDp = async () => {
    setSyncing(true);
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/baseline/sync-dp-logics");
      setMsg({ text: data.detail || "Sync complete", type: "success" });
      if (data.sidecars) setSidecars(data.sidecars);
      await load(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Sync failed", type: "danger" });
    } finally {
      setSyncing(false);
    }
  };

  const fetchPrevious = async () => {
    setFetchingPrev(true);
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/baseline/generate/fetch-previous-baseline", {
        target_week: targetWeek,
        target_year: targetYear,
      });
      setPrevPreview(data);
      setMsg({ text: `Previous baseline loaded — ${Number(data.rows || 0).toLocaleString()} rows`, type: "success" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Fetch previous failed", type: "danger" });
      setPrevPreview(null);
    } finally {
      setFetchingPrev(false);
    }
  };

  if (!mounted) {
    return (
      <AppShell
        title="Configure Parameters"
        subtitle="Base sheet sync, pipeline toggles and DP Logics worksheet sync"
        actions={
          <button type="button" className="btn btn-secondary btn-sm" disabled>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      >
        <SectionCard title="Edit Parameters" description="Saved to Pipeline Params Google Sheet.">
          <span className="spinner" />
        </SectionCard>
      </AppShell>
    );
  }

  return (
    <AppShell
      title="Configure Parameters"
      subtitle="Base sheet sync, pipeline toggles and DP Logics worksheet sync"
      actions={
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => load(true)} disabled={loading || refreshing}>
          <RefreshCw size={13} className={loading || refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {/* ── Pipeline Parameters tab ───────────────────────────────────────── */}
        <>
          {msg.text && <div className={`alert alert-${msg.type} mb-4`}>{msg.text}</div>}

          {!activeReady && (
            <div className="alert alert-warning text-sm mb-4">
              No active dataset found — run <strong>Generate Baseline</strong> or load data first.
            </div>
          )}

          <SectionCard title="Edit Parameters" description="Saved to Pipeline Params Google Sheet.">
            {loading && !data ? (
              <span className="spinner" />
            ) : (
              <>
                <div className="grid-2 mb-4">
                  {(
                    [
                      ["use_clustering", "Use Clustering"],
                      ["remove_outliers", "Remove Outliers"],
                      ["apply_hub_changes", "Apply Hub & KML Changes"],
                      ["use_availability", "Use Availability"],
                      ["use_stf", "Use Sell-Through Factor"],
                      ["use_percentile", "Use Percentile"],
                    ] as const
                  ).map(([key, label]) => (
                    <label key={key} style={{ display: "flex", gap: "0.5rem" }} className="text-sm">
                      <input
                        type="checkbox"
                        checked={flags[key]}
                        onChange={e => setFlags(f => ({ ...f, [key]: e.target.checked }))}
                        disabled={readOnly}
                      />
                      {label}
                    </label>
                  ))}
                </div>
                <div className="grid-2" style={{ maxWidth: 400 }}>
                  <div className="form-group">
                    <label className="form-label">Weeks Back</label>
                    <input
                      type="number"
                      className="form-input"
                      value={flags.weeks_back}
                      onChange={e => setFlags(f => ({ ...f, weeks_back: Number(e.target.value) }))}
                      disabled={readOnly}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Availability Threshold</label>
                    <input
                      type="number"
                      step="0.01"
                      className="form-input"
                      value={flags.avail_threshold}
                      onChange={e => setFlags(f => ({ ...f, avail_threshold: Number(e.target.value) }))}
                      disabled={readOnly}
                    />
                  </div>
                </div>
                <button type="button" className="btn btn-primary mt-3" onClick={saveParams} disabled={readOnly || saving}>
                  {saving ? "Saving…" : "Save Parameters"}
                </button>
              </>
            )}
          </SectionCard>

          <SectionCard title="Parameters from Google Sheet">
            {Object.keys(data?.params || {}).length > 0 && (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
                  <tbody>
                    {Object.entries(data?.params || {}).map(([k, v]) => (
                      <tr key={k}><td>{k}</td><td style={{ fontSize: "0.8rem" }}>{String(v)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          <SectionCard title="Configuration Masters" description="Sync individual or all logics worksheets from DP Logics Google Sheet.">
            {/* Group tabs */}
            {masterGroups.length > 1 && (
              <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl mb-4 w-fit">
                {masterGroups.map((g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => setActiveMasterGroup(g)}
                    className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-all
                      ${activeMasterGroup === g
                        ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-sm"
                        : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                      }`}
                  >
                    {g}
                    <span className={`ml-1.5 text-[10px] font-semibold px-1.5 py-0.5 rounded-full
                      ${activeMasterGroup === g ? "bg-blue-100 text-blue-700" : "bg-slate-200 text-slate-500"}`}>
                      {dpStatus.filter((s) => s.group === g).length}
                    </span>
                  </button>
                ))}
              </div>
            )}

            <div className="space-y-3">
              {visibleMasterStatus.map((row) => {
                const isBusy = !!masterSyncBusy[row.worksheet];
                const msg = masterSyncMessages[row.worksheet];
                const isSaved = row.status === "saved";

                return (
                  <div
                    key={row.worksheet}
                    className={`bg-white dark:bg-slate-900 border rounded-xl p-4 transition-all duration-200
                      ${isBusy
                        ? "border-blue-300 dark:border-blue-600 shadow-md shadow-blue-100 dark:shadow-blue-950"
                        : "border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md hover:border-slate-300 dark:hover:border-slate-700"
                      }`}
                  >
                    <div className="flex items-center gap-4">
                      {/* Icon */}
                      <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center flex-shrink-0">
                        <Database size={15} className="text-blue-600 dark:text-blue-400" />
                      </div>

                      {/* Label + last sync */}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 leading-tight">
                          {row.label || row.worksheet}
                        </p>
                        {row.last_sync ? (
                          <div className="flex items-center gap-1.5 mt-0.5 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
                            <Clock size={10} className="flex-shrink-0" />
                            <span>{formatIST(row.last_sync.started_at || "")}</span>
                            <span className="text-slate-300 dark:text-slate-600">·</span>
                            <span className="font-medium text-slate-700 dark:text-slate-300 max-w-[180px] truncate">
                              {row.last_sync.email || row.last_sync.full_name}
                            </span>
                            <span className="text-slate-300 dark:text-slate-600">·</span>
                            <span className={`font-semibold ${row.last_sync.status === "success" ? "text-emerald-600 dark:text-emerald-400" : "text-red-500 dark:text-red-400"}`}>
                              {row.last_sync.status === "success" ? "✓ Synced" : "✗ Failed"}
                            </span>
                          </div>
                        ) : row.last_updated ? (
                          <div className="flex items-center gap-1.5 mt-0.5 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
                            <Clock size={10} className="flex-shrink-0" />
                            <span>Last updated: {formatIST(row.last_updated)}</span>
                            <span className="text-slate-300 dark:text-slate-600">·</span>
                            <span className={`font-semibold ${isSaved ? "text-emerald-600" : "text-slate-700 dark:text-slate-300"}`}>
                              {isSaved ? "✓ Saved" : "Pending sync"}
                            </span>
                          </div>
                        ) : (
                          <p className="text-xs text-slate-400 dark:text-slate-600 italic mt-0.5">Never synced</p>
                        )}
                      </div>

                      {/* Open link */}
                      {row.url && (
                        <a
                          href={row.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hidden sm:inline-flex items-center gap-1 text-xs font-medium text-blue-600 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg px-2.5 py-1.5 hover:bg-blue-100 transition-colors whitespace-nowrap"
                        >
                          <ExternalLink size={11} />
                          Open Sheet
                        </a>
                      )}

                      {/* Sync button */}
                      <button
                        type="button"
                        disabled={readOnly || isBusy}
                        onClick={() => handleSyncMaster(row.worksheet)}
                        className="inline-flex items-center gap-1.5 text-xs font-semibold px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white transition-colors whitespace-nowrap shadow-sm"
                      >
                        {isBusy
                          ? <span className="spinner" style={{ width: 11, height: 11, borderTopColor: "white" }} />
                          : <FileSpreadsheet size={11} />
                        }
                        {isBusy ? "Syncing…" : "Sync Now"}
                      </button>
                    </div>

                    {/* Status message */}
                    {msg && (
                      <div className="mt-3">
                        {msg.type === "success" ? (
                          <div className="flex items-center gap-2 text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 rounded-lg px-3 py-2">
                            <CheckCircle2 size={13} className="flex-shrink-0" />
                            <span>
                              Sync complete — saved to{" "}
                              <code className="font-mono bg-emerald-100 dark:bg-emerald-900 px-1 rounded text-[11px]">base_sheet_baseline/</code>
                            </span>
                          </div>
                        ) : (
                          <div className="flex items-start gap-2 text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
                            <XCircle size={13} className="flex-shrink-0 mt-0.5" />
                            <span>Sync failed: <span className="font-medium">{msg.text}</span></span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {sidecars.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-semibold mb-2">Engine sidecars refreshed</p>
                <ul className="text-xs text-muted">
                  {sidecars.map((s, i) => <li key={i}>{JSON.stringify(s)}</li>)}
                </ul>
              </div>
            )}
            {/* <p className="text-xs text-muted mt-3">
              Hub changes are edited under <a href="/master-data?tab=demand">Master Data → Hub Changes</a>.
            </p> */}
          </SectionCard>

          <SectionCard title="Previous Baseline Cache">
            <p className="text-xs text-muted mb-3">
              Pre-fetch prior-week BasePlan into <code>prev_baseline_latest.parquet</code> before running the engine.
            </p>
            <div className="grid-2 mb-3" style={{ maxWidth: 400 }}>
              <div className="form-group">
                <label className="form-label">Target ISO Week</label>
                <input type="number" className="form-input" value={targetWeek}
                  onChange={e => setTargetWeek(Number(e.target.value))} disabled={readOnly} />
              </div>
              <div className="form-group">
                <label className="form-label">Target Year</label>
                <input type="number" className="form-input" value={targetYear}
                  onChange={e => setTargetYear(Number(e.target.value))} disabled={readOnly} />
              </div>
            </div>
            <button type="button" className="btn btn-secondary" disabled={readOnly || fetchingPrev} onClick={fetchPrevious}>
              <RefreshCw size={14} className={fetchingPrev ? "animate-spin" : ""} />
              {fetchingPrev ? "Fetching…" : "Fetch Previous Baseline"}
            </button>
            {prevPreview && (
              <p className="text-sm mt-3">
                Loaded <strong>{Number(prevPreview.rows || 0).toLocaleString()}</strong> rows · BasePlan sum{" "}
                {Number(prevPreview.base_plan_sum || 0).toLocaleString()}
              </p>
            )}
          </SectionCard>
        </>
      </AppShell>
    );
}

export default function ConfigurePage() {
  return (
    <Suspense>
      <ConfigureContent />
    </Suspense>
  );
}
