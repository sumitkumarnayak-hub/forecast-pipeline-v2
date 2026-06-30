"use client";

import { useCallback, useEffect, useRef, useState, type ElementType } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import api from "@/lib/api";
import { cacheGet, cacheInvalidate, cacheSet } from "@/lib/queryCache";
import { useAuth } from "@/hooks/useAuth";
import {
  Zap,
  Loader2,
  RefreshCw,
  FolderOpen,
  MousePointer2,
  Play,
  RotateCcw,
  CornerUpLeft,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  ExternalLink,
  ClipboardList,
  History,
  Terminal,
  Download,
  Settings,
  Calculator,
  Mail,
  Rocket,
  CheckCircle2,
  XCircle,
  Circle,
  Clock,
} from "lucide-react";

import { createDefaultBootstrap } from "@/lib/autopilotDefaults";
import {
  AUTOPILOT_MANUAL_STEPS,
  manualLinkForStepIndex,
  manualLinkForStepKey,
} from "@/lib/autopilotManualLinks";
import type { Bootstrap, UiStatus } from "@/app/autopilot/types";

type TabId = "run" | "history" | "manual";

interface HistoryRow {
  "Run ID": string;
  Name: string;
  Status: string;
  Steps: number;
  User: string;
  Started: string;
  Completed: string;
  Source: string;
}

const STEP_ICONS: Record<string, ElementType> = {
  clipboard: ClipboardList,
  rocket: Rocket,
  download: Download,
  settings: Settings,
  calculator: Calculator,
  mail: Mail,
};

const STATUS_META: Record<string, { label: string; pill: string; node: string; Icon: ElementType }> = {
  done: {
    label: "Done",
    pill: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200",
    node: "bg-emerald-50 border-emerald-500 text-emerald-800",
    Icon: CheckCircle2,
  },
  running: {
    label: "Running",
    pill: "bg-blue-100 text-blue-800 ring-1 ring-blue-200",
    node: "bg-blue-50 border-blue-500 text-blue-800",
    Icon: Loader2,
  },
  failed: {
    label: "Failed",
    pill: "bg-red-100 text-red-800 ring-1 ring-red-200",
    node: "bg-red-50 border-red-500 text-red-800",
    Icon: XCircle,
  },
  queued: {
    label: "Queued",
    pill: "bg-slate-100 text-slate-500 ring-1 ring-slate-200",
    node: "bg-slate-50 border-slate-300 text-slate-500",
    Icon: Clock,
  },
  ready: {
    label: "Ready",
    pill: "bg-slate-100 text-slate-600 ring-1 ring-slate-200",
    node: "bg-white border-slate-200 text-slate-600",
    Icon: Circle,
  },
};

function statusBanner(status: UiStatus) {
  switch (status) {
    case "running":
      return { label: "Running", cls: "text-blue-600" };
    case "failed":
      return { label: "Failed — try again", cls: "text-red-600" };
    case "success":
      return { label: "Completed", cls: "text-emerald-600" };
    default:
      return { label: "Ready", cls: "text-slate-500" };
  }
}

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-slate-200/80 ${className}`} />;
}

export default function AutopilotPage() {
  const { readOnly } = useAuth();
  const [tab, setTab] = useState<TabId>("run");
  const [boot, setBoot] = useState<Bootstrap>(() => createDefaultBootstrap(true));
  const [stateLoading, setStateLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [selectedRun, setSelectedRun] = useState("");
  const [runDetail, setRunDetail] = useState<Record<string, unknown> | null>(null);
  const [msg, setMsg] = useState("");
  const [showLog, setShowLog] = useState(false);
  const [showPaths, setShowPaths] = useState(false);
  const [runLog, setRunLog] = useState("");
  const [logLoading, setLogLoading] = useState(false);
  const [errorTrace, setErrorTrace] = useState("");
  const [loadError, setLoadError] = useState("");
  const [fromStep, setFromStep] = useState(0);
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fetchSeq = useRef(0);
  const startingRef = useRef(false);
  const activeRunRef = useRef<string | null>(null);

  const loadRunLog = useCallback(async (runId: string) => {
    setLogLoading(true);
    try {
      const { data } = await api.get(`/api/autopilot/runs/${runId}/log`);
      setRunLog(data.log_text || "");
    } catch {
      setRunLog("");
    } finally {
      setLogLoading(false);
    }
  }, []);

  const toggleLog = () => {
    const next = !showLog;
    setShowLog(next);
    const rid = (boot?.state?.run_id as string) || activeRunRef.current;
    if (next && rid) loadRunLog(rid);
  };

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const fetchBootstrap = useCallback(async (silent = false, refresh = false) => {
    const cacheKey = "autopilot:bootstrap-shell";

    if (!refresh) {
      const cached = cacheGet<Bootstrap>(cacheKey);
      if (cached) {
        setBoot(prev => ({
          ...prev,
          ...cached,
          state: prev.state,
          ui_status: prev.ui_status,
          step_rows: prev.step_rows,
          step_idx: prev.step_idx,
          progress_pct: prev.progress_pct,
          resume_step: prev.resume_step,
        }));
      }
    } else {
      cacheInvalidate(cacheKey);
    }

    if (!silent) setRefreshing(true);

    try {
      const { data } = await api.get<Bootstrap>("/api/autopilot/bootstrap", {
        params: refresh ? { refresh: true } : undefined,
      });
      cacheSet(cacheKey, data, 120_000);
      setBoot(prev => ({
        ...prev,
        ...data,
        state: prev.state,
        ui_status: prev.ui_status,
        resume_step: prev.resume_step,
        step_idx: prev.step_idx,
        progress_pct: prev.progress_pct,
        step_rows: prev.step_rows,
      }));
      setLoadError("");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setLoadError(err?.response?.data?.detail || "Failed to load Auto-Pilot config");
    } finally {
      if (!silent) setRefreshing(false);
    }
  }, []);

  const fetchRunState = useCallback(async (silent = false, refresh = false) => {
    const stateCacheKey = "autopilot:run-state";
    if (!refresh && !silent) {
      const cached = cacheGet<{
        state: Record<string, unknown> | null;
        ui_status: UiStatus;
        resume_step: number | null;
        step_idx: number;
        progress_pct: number;
        step_rows: Bootstrap["step_rows"];
      }>(stateCacheKey);
      if (cached) {
        setBoot(prev => ({
          ...prev,
          state: cached.state,
          ui_status: cached.ui_status,
          resume_step: cached.resume_step,
          step_idx: cached.step_idx,
          progress_pct: cached.progress_pct,
          step_rows: cached.step_rows,
        }));
        setStateLoading(false);
      } else if (!silent) {
        setStateLoading(true);
      }
    } else if (!silent) {
      setStateLoading(true);
    }
    try {
      const { data } = await api.get<{
        state: Record<string, unknown> | null;
        ui_status: UiStatus;
        resume_step: number | null;
        step_idx: number;
        progress_pct: number;
        step_rows: Bootstrap["step_rows"];
      }>("/api/autopilot/state", {
        params: refresh ? { refresh: true } : undefined,
      });
      cacheSet(stateCacheKey, data, 15_000);
      setBoot(prev => ({
        ...prev,
        state: data.state,
        ui_status: data.ui_status,
        resume_step: data.resume_step,
        step_idx: data.step_idx,
        progress_pct: data.progress_pct,
        step_rows: data.step_rows,
      }));
      setLoadError("");
      setErrorTrace("");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      const detail = err?.response?.data?.detail;
      if (detail) setLoadError(detail);
    } finally {
      if (!silent) setStateLoading(false);
    }
  }, []);

  const fetchHistory = useCallback(async (refresh = false) => {
    setHistoryLoading(true);
    try {
      const histRes = await api.get("/api/autopilot/history", {
        params: { limit: 30, ...(refresh ? { refresh: true } : {}) },
      });
      const rows: HistoryRow[] = histRes.data.rows || [];
      setHistory(rows);
      setHistoryLoaded(true);
      if (rows.length) {
        setSelectedRun(prev => prev || rows[0]["Run ID"]);
      }
    } catch {
      // History is secondary — don't block the run tab
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const fetchPageData = useCallback(
    async (silent = false, refresh = false) => {
      if (!silent) setRefreshing(true);
      try {
        await Promise.all([
          fetchBootstrap(true, refresh),
          fetchRunState(true, refresh),
        ]);
        if (tab === "history") await fetchHistory(refresh);
      } finally {
        if (!silent) setRefreshing(false);
      }
    },
    [fetchBootstrap, fetchRunState, fetchHistory, tab],
  );

  useEffect(() => {
    void fetchBootstrap();
    void fetchRunState();
    return () => {
      esRef.current?.close();
      stopPolling();
    };
  }, [fetchBootstrap, fetchRunState, stopPolling]);

  useEffect(() => {
    if (tab === "history" && !historyLoaded && !historyLoading) {
      fetchHistory();
    }
  }, [tab, historyLoaded, historyLoading, fetchHistory]);

  useEffect(() => {
    if (!selectedRun) return;
    const ac = new AbortController();
    api
      .get(`/api/autopilot/runs/${selectedRun}`, { signal: ac.signal })
      .then(r => setRunDetail(r.data))
      .catch(() => {
        if (!ac.signal.aborted) setRunDetail(null);
      });
    return () => ac.abort();
  }, [selectedRun]);

  const subscribeRun = (runId: string) => {
    esRef.current?.close();
    const es = new EventSource(`/api/autopilot/stream/${runId}`, { withCredentials: true });
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data);
        if (payload.event === "log") {
          setRunLog(payload.text || "");
        } else if (payload.event === "completed") {
          setMsg("All 6 steps completed successfully.");
          es.close();
          activeRunRef.current = null;
          stopPolling();
          void fetchRunState(true, true);
        } else if (payload.event === "failed") {
          setMsg(payload.error || "Pipeline failed");
          if (payload.error) setErrorTrace(payload.error);
          es.close();
          activeRunRef.current = null;
          stopPolling();
          void fetchRunState(true, true);
        } else if (payload.event === "step") {
          const lines = [payload.message].filter(Boolean);
          if (Array.isArray(payload.metric_lines)) {
            for (const line of payload.metric_lines) {
              lines.push(`• ${line}`);
            }
          }
          if (payload.warning) {
            lines.push(`⚠ ${payload.warning}`);
          }
          if (lines.length) setMsg(lines.join("\n"));
          void fetchRunState(true, true);
          if (payload.status === "failed") {
            setErrorTrace(payload.error || payload.message || "");
          }
        }
      } catch {
        // ignore malformed SSE payloads
      }
    };
    es.onerror = () => {
      es.close();
      stopPolling();
      void fetchRunState(true, true);
    };
  };

  const startPolling = () => {
    stopPolling();
    pollRef.current = setInterval(() => void fetchRunState(true, true), 2500);
  };

  const startAction = async (action: "run" | "resume" | "retry" | "restart") => {
    if (startingRef.current) return;
    startingRef.current = true;
    setMsg("");
    setErrorTrace("");
    setLoadError("");
    setBoot(prev => (prev ? { ...prev, ui_status: "running" } : prev));
    try {
      const { data } = await api.post("/api/autopilot/run", {
        action,
        run_id: boot?.state?.run_id,
        from_step: action === "run" ? fromStep : undefined,
      });
      activeRunRef.current = data.run_id;
      subscribeRun(data.run_id);
      startPolling();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg(err?.response?.data?.detail || "Failed to start pipeline");
      fetchRunState(true);
    } finally {
      startingRef.current = false;
    }
  };

  const uiStatus = boot.ui_status ?? "idle";
  const banner = statusBanner(uiStatus);
  const runId = (boot.state?.run_id as string) || "";
  const total = boot.steps_config?.length ?? 6;
  const stepIdx = boot.step_idx ?? 0;
  const progress = boot.progress_pct ?? 0;
  const failedStepIndex =
    boot.state?.failed_step != null ? Number(boot.state.failed_step) : null;
  const failedManualLink =
    failedStepIndex != null ? manualLinkForStepIndex(failedStepIndex) : null;
  const pathsRef = (boot as Bootstrap & { output_paths_reference?: { step: string; label: string; path: string }[] })
    .output_paths_reference;

  const tabs: { id: TabId; label: string; icon: ElementType }[] = [
    { id: "run", label: "Current run", icon: Zap },
    { id: "history", label: "Run history", icon: History },
    { id: "manual", label: "Manual workflow", icon: MousePointer2 },
  ];

  const actionButtons = (
    <div className="flex flex-wrap items-center gap-2">
      {!readOnly && uiStatus === "idle" && (
        <>
          <div className="form-group mb-3" style={{ maxWidth: 220 }}>
            <label className="form-label text-xs">Start from step (1–6)</label>
            <select className="form-input text-sm" value={fromStep} onChange={e => setFromStep(Number(e.target.value))}>
              {[0, 1, 2, 3, 4, 5].map(n => (
                <option key={n} value={n}>
                  Step {n + 1}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => startAction("run")}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            <Play className="h-4 w-4" />
            Run pipeline
          </button>
          {boot?.resume_step != null && boot.resume_step > 0 && (
            <button
              type="button"
              onClick={() => startAction("resume")}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
            >
              <CornerUpLeft className="h-4 w-4" />
              Resume from step {boot.resume_step + 1}
            </button>
          )}
        </>
      )}
      {!readOnly && uiStatus === "failed" && (
        <>
          <button
            type="button"
            onClick={() => startAction("retry")}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
          >
            <RotateCcw className="h-4 w-4" />
            Try again
          </button>
          <button
            type="button"
            onClick={() => startAction("restart")}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
          >
            Restart from step 1
          </button>
        </>
      )}
      {!readOnly && uiStatus === "success" && (
        <button
          type="button"
          onClick={() => startAction("restart")}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
        >
          <Play className="h-4 w-4" />
          Run again
        </button>
      )}
      <button
        type="button"
        onClick={() => void fetchPageData(false, true)}
        disabled={refreshing || stateLoading}
        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 disabled:opacity-50"
      >
        <RefreshCw className={`h-4 w-4 ${refreshing || stateLoading ? "animate-spin" : ""}`} />
        Refresh
      </button>
    </div>
  );

  const runTabContent = (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.6fr_1fr]">
      {stateLoading && (
        <div className="xl:col-span-2 rounded-lg border border-blue-100 bg-blue-50 px-4 py-2 text-sm text-blue-800">
          Loading run status…
        </div>
      )}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {readOnly && (
          <div className="mb-5 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            Read-only access — pipeline runs are disabled for your role.
          </div>
        )}

        {actionButtons}

        {boot?.resume_step != null && uiStatus === "idle" && !readOnly && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Previous run did not finish — resume from step {boot.resume_step + 1} without re-running earlier steps.
          </div>
        )}

        {msg && (
          <div
            className={`mt-4 rounded-lg border px-4 py-3 text-sm ${
              msg.toLowerCase().includes("success")
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-red-200 bg-red-50 text-red-800"
            }`}
          >
            {msg}
          </div>
        )}

        {runId && (
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className={`text-sm font-bold ${banner.cls}`}>{banner.label}</span>
              <span className="text-sm text-slate-500">
                {progress}% · {Math.min(stepIdx, total)}/{total}
              </span>
            </div>
            <code className="rounded bg-white px-2 py-1 text-xs text-slate-500 ring-1 ring-slate-200">
              {runId.slice(0, 28)}…
            </code>
          </div>
        )}

        <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-blue-600 transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Pipeline nodes — Streamlit-style horizontal stepper */}
        <div className="mt-6 flex items-stretch gap-0 overflow-x-auto pb-2">
          {boot?.steps_config?.map((cfg, i) => {
            const row = boot.step_rows?.[i];
            const vis = row?.status || "ready";
            const meta = STATUS_META[vis] || STATUS_META.ready;
            const StepIcon = STEP_ICONS[cfg.icon] || ClipboardList;
            const short = cfg.name.split(": ").pop() || cfg.name;
            return (
              <div key={i} className="flex items-center shrink-0">
                <div
                  className={`flex w-[100px] flex-col items-center rounded-lg border-2 px-2 py-3 text-center ${meta.node}`}
                >
                  <StepIcon className="mb-1.5 h-5 w-5" />
                  <span className="text-[0.65rem] font-bold leading-tight">{short.slice(0, 24)}</span>
                </div>
                {i < (boot?.steps_config?.length ?? 0) - 1 && (
                  <ChevronRight className="mx-0.5 h-4 w-4 shrink-0 text-slate-300" />
                )}
              </div>
            );
          })}
        </div>

        {/* Steps table */}
        <div className="mt-6 overflow-hidden rounded-lg border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 w-10">#</th>
                <th className="px-4 py-3">Step</th>
                <th className="px-4 py-3 w-28">Status</th>
                <th className="px-4 py-3">Detail</th>
                <th className="px-4 py-3 w-32">Manual</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {boot?.step_rows?.map(row => {
                const meta = STATUS_META[row.status] || STATUS_META.ready;
                const manual = manualLinkForStepKey(row.key);
                return (
                  <tr key={row.index} className="hover:bg-slate-50/80">
                    <td className="px-4 py-3 font-medium text-slate-500">{row.index + 1}</td>
                    <td className="px-4 py-3 font-medium text-slate-800">
                      {row.name.split(": ").pop()}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${meta.pill}`}>
                        {meta.label}
                      </span>
                    </td>
                    <td className="max-w-md px-4 py-3 text-slate-600">{row.detail || "—"}</td>
                    <td className="px-4 py-3">
                      {manual ? (
                        <Link
                          href={manual.href}
                          className={`text-xs font-semibold hover:underline ${
                            row.status === "failed" ? "text-red-700" : "text-blue-600"
                          }`}
                        >
                          {manual.label}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {uiStatus === "failed" && failedManualLink && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
            <div>
              <span className="font-semibold">
                Step {(failedStepIndex ?? 0) + 1} failed
              </span>
              {" — "}
              {boot.step_rows?.[failedStepIndex ?? 0]?.detail || "See log for details."}
            </div>
            <Link
              href={failedManualLink.href}
              className="inline-flex items-center gap-1.5 rounded-lg bg-red-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-800"
            >
              Fix in {failedManualLink.label}
              <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}

        {uiStatus === "failed" && errorTrace && (
          <details className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-red-800">Error trace</summary>
            <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap font-mono text-xs text-red-900">
              {errorTrace}
            </pre>
          </details>
        )}

        {(runId || uiStatus === "running") && pathsRef && pathsRef.length > 0 && (
          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">
              Step output paths
            </div>
            <ul className="space-y-1 text-xs text-slate-600">
              {pathsRef.map((ref, i) => (
                <li key={i}>
                  <span className="font-medium text-slate-700">{ref.step}</span>
                  {" · "}
                  {ref.label}: <code className="text-[0.65rem]">{ref.path}</code>
                </li>
              ))}
            </ul>
          </div>
        )}

        {(runId || activeRunRef.current) && (
          <div className="mt-4">
            <button
              type="button"
              onClick={toggleLog}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-600 hover:text-blue-700"
            >
              {showLog ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              Live run log
              {logLoading && <Loader2 className="h-3 w-3 animate-spin" />}
            </button>
            {showLog && (
              <pre className="mt-2 max-h-72 overflow-auto rounded-lg border border-slate-200 bg-slate-900 p-4 font-mono text-xs leading-relaxed text-slate-100 whitespace-pre-wrap">
                {runLog || "No log lines yet."}
              </pre>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4">
        {boot?.output_paths && (
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-800">
              <FolderOpen className="h-4 w-4 text-blue-600" />
              Output paths
            </div>
            {(
              [
                ["Product Masters", boot.output_paths.ff_masters_xlsx],
                ["Raw Actuals", boot.output_paths.raw_actuals_folder],
                ["DP Logics", boot.output_paths.dp_logics_folder],
                ["Baseline Outputs", boot.output_paths.baseline_outputs_folder],
              ] as const
            ).map(([label, path]) => (
              <div key={label} className="mb-3 last:mb-0">
                <div className="text-[0.65rem] font-bold uppercase tracking-wider text-slate-400">{label}</div>
                <div className="mt-1 break-all rounded-md bg-slate-50 px-2.5 py-1.5 font-mono text-xs text-slate-600 ring-1 ring-slate-200">
                  {path || "—"}
                </div>
              </div>
            ))}
            {boot.output_paths.pipeline_params_sheet_url && (
              <a
                href={boot.output_paths.pipeline_params_sheet_url}
                target="_blank"
                rel="noreferrer"
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
              >
                <ExternalLink className="h-4 w-4" />
                Pipeline Params Sheet
              </a>
            )}
            <button
              type="button"
              onClick={() => setShowPaths(v => !v)}
              className="mt-3 text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              {showPaths ? "Hide" : "Show"} per-step reference
            </button>
            {showPaths && boot.output_paths_reference && (
              <ul className="mt-2 space-y-1.5 text-xs text-slate-600">
                {boot.output_paths_reference.map((p, i) => (
                  <li key={i}>
                    <span className="font-semibold text-slate-700">{p.step}</span> · {p.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="rounded-xl border border-blue-100 bg-gradient-to-br from-blue-50 to-white p-5 shadow-sm">
          <div className="mb-2 flex items-center gap-2 text-sm font-bold text-blue-900">
            <Terminal className="h-4 w-4" />
            CLI alternative
          </div>
          <p className="mb-2 text-xs text-slate-500">Task-scheduler friendly:</p>
          <pre className="overflow-x-auto rounded-lg bg-white/90 p-3 font-mono text-xs text-slate-700 ring-1 ring-blue-100">{`python scripts/run_optimized_autopilot.py
python scripts/run_optimized_autopilot.py --from-step 2`}</pre>
        </div>
      </div>
    </div>
  );

  const historyTabContent = (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      {historyLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : history.length === 0 ? (
        <p className="text-sm text-slate-500">No pipeline runs recorded yet.</p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  {["Run ID", "Name", "Status", "Steps", "User", "Started", "Source"].map(h => (
                    <th key={h} className="px-4 py-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {history.map(row => (
                  <tr
                    key={row["Run ID"]}
                    className={`cursor-pointer transition hover:bg-slate-50 ${selectedRun === row["Run ID"] ? "bg-blue-50/50" : ""}`}
                    onClick={() => setSelectedRun(row["Run ID"])}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-slate-600">{row["Run ID"]}</td>
                    <td className="px-4 py-3">{row.Name}</td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium capitalize">
                        {row.Status}
                      </span>
                    </td>
                    <td className="px-4 py-3">{row.Steps}</td>
                    <td className="px-4 py-3">{row.User}</td>
                    <td className="px-4 py-3 text-slate-500">{row.Started}</td>
                    <td className="px-4 py-3 text-xs uppercase text-slate-500">{row.Source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {runDetail && (
            <div className="mt-6">
              <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                {[
                  ["Status", String(runDetail.status || "—")],
                  ["Steps done", Array.isArray(runDetail.completed_steps) ? runDetail.completed_steps.length : 0],
                  ["Source", String(runDetail.source || "—").toUpperCase()],
                ].map(([label, val]) => (
                  <div key={label as string} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</div>
                    <div className="mt-1 text-lg font-bold text-slate-800">{val}</div>
                  </div>
                ))}
              </div>
              {Boolean(runDetail.log_text) && (
                <pre className="max-h-72 overflow-auto rounded-lg bg-slate-900 p-4 font-mono text-xs text-slate-100 whitespace-pre-wrap">
                  {String(runDetail.log_text)}
                </pre>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );

  const manualTabContent = (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="text-lg font-bold text-slate-800">Manual workflow</h3>
      <p className="mt-1 max-w-2xl text-sm text-slate-500">
        Run each Auto-Pilot step individually. After a failed run, use the matching step below to fix data and resume.
      </p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {AUTOPILOT_MANUAL_STEPS.map(step => (
          <Link
            key={step.key}
            href={step.href}
            className="group rounded-lg border border-slate-200 p-4 transition hover:border-blue-300 hover:bg-blue-50/40"
          >
            <div className="text-xs font-bold text-blue-600">Step {step.index + 1}</div>
            <div className="mt-1 font-semibold text-slate-800 group-hover:text-blue-700">{step.label}</div>
            <p className="mt-1 text-xs text-slate-500">{step.description}</p>
          </Link>
        ))}
      </div>
      <div className="mt-6 flex flex-wrap gap-3 border-t border-slate-100 pt-6">
        <Link href="/baseline/load-raw" className="btn btn-secondary btn-sm">
          <Calculator className="h-4 w-4" /> Full baseline wizard
        </Link>
        <Link href="/master-data" className="btn btn-secondary btn-sm">
          <ClipboardList className="h-4 w-4" /> Master Data hub
        </Link>
      </div>
    </div>
  );

  return (
    <AppShell
      title="Auto-Pilot"
      subtitle="6-step automated baseline pipeline"
      actions={
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={refreshing || stateLoading}
          onClick={() => void fetchPageData(false, true)}
        >
          <RefreshCw size={13} className={refreshing || stateLoading ? "animate-spin" : ""} />
          Refresh
        </button>
      }
    >
      {/* Tab bar */}
      <div className="mb-6 flex flex-wrap gap-1 border-b border-slate-200 bg-white rounded-t-xl px-2 pt-2">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`-mb-px inline-flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold transition-colors focus:outline-none ${
              tab === id
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {loadError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {loadError}
          <button
            type="button"
            onClick={() => fetchPageData()}
            className="ml-3 font-semibold text-red-900 underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {tab === "run" && runTabContent}
      {tab === "history" && historyTabContent}
      {tab === "manual" && manualTabContent}
    </AppShell>
  );
}
