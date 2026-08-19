"use client";

import { Suspense, useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import SectionCard from "@/components/baseline/SectionCard";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  Play,
  RefreshCw,
  Terminal,
  CheckCircle2,
  XCircle,
  Clock,
  Activity,
  Layers,
} from "lucide-react";

interface PipelineRunItem {
  run_id: string;
  triggered_by: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  step1_status: string;
  step2_status: string;
  step3_status: string;
}

interface LogDetail {
  run_id: string;
  triggered_by: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  step1_status: string;
  step2_status: string;
  step3_status: string;
  console_log: string;
}

export default function PipelineRunsPage() {
  return (
    <Suspense>
      <PipelineRunsInner />
    </Suspense>
  );
}

function PipelineRunsInner() {
  const { user } = useAuth();
  const [runs, setRuns] = useState<PipelineRunItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [logDetail, setLogDetail] = useState<LogDetail | null>(null);
  const [loadingLog, setLoadingLog] = useState(false);

  const isReadOnly = user?.role === "viewer";

  const fetchRuns = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<{ runs: PipelineRunItem[] }>("/api/pipeline/runs?limit=50");
      const list = data.runs || [];
      setRuns(list);
      if (list.length > 0) {
        handleViewLog(list[0].run_id);
      }
    } catch (err) {
      console.error("Failed fetching pipeline runs:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRuns();
  }, []);

  const handleRunNow = async () => {
    if (isReadOnly || triggering) return;
    setTriggering(true);
    try {
      await api.post("/api/pipeline/run?triggered_by=Portal UI");
      await fetchRuns();
    } catch (err) {
      console.error("Failed triggering pipeline run:", err);
    } finally {
      setTriggering(false);
    }
  };

  const handleViewLog = async (runId: string) => {
    setSelectedRunId(runId);
    setLoadingLog(true);
    try {
      const { data } = await api.get<LogDetail>(`/api/pipeline/runs/${runId}/log`);
      setLogDetail(data);
    } catch (err) {
      console.error("Failed loading log detail:", err);
    } finally {
      setLoadingLog(false);
    }
  };

  const renderStepBadge = (status: string, label: string) => {
    let colorClass = "bg-secondary text-secondary-foreground";
    let icon = <Clock size={12} className="mr-1" />;
    if (status === "completed") {
      colorClass = "bg-green-500/10 text-green-500 border border-green-500/20";
      icon = <CheckCircle2 size={12} className="mr-1" />;
    } else if (status === "failed") {
      colorClass = "bg-red-500/10 text-red-500 border border-red-500/20";
      icon = <XCircle size={12} className="mr-1" />;
    } else if (status === "running") {
      colorClass = "bg-blue-500/10 text-blue-500 border border-blue-500/20 animate-pulse";
      icon = <RefreshCw size={12} className="mr-1 animate-spin" />;
    }

    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${colorClass}`}>
        {icon}
        {label}
      </span>
    );
  };

  return (
    <AppShell
      title="Pipeline Execution Runs & Logs"
      subtitle="Monitor 3-step forecasting pipeline runs triggered by GitHub Actions, Apache Airflow, CLI, or Portal UI"
    >

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SectionCard title="Total Executions">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-muted">Total Recorded Runs</div>
              <div className="text-2xl font-bold mt-1">{runs.length}</div>
            </div>
            <div className="p-3 rounded-lg bg-primary/10 text-primary">
              <Layers size={20} />
            </div>
          </div>
        </SectionCard>

        <SectionCard title="Latest Execution Status">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-muted">Latest Execution Status</div>
              <div className="text-sm font-semibold mt-1">
                {runs.length > 0 ? (
                  <span className="capitalize">{runs[0].status}</span>
                ) : (
                  "No runs recorded"
                )}
              </div>
            </div>
            <div className="p-3 rounded-lg bg-green-500/10 text-green-500">
              <CheckCircle2 size={20} />
            </div>
          </div>
        </SectionCard>

        <SectionCard title="Manual Trigger">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-muted">Manual Trigger</div>
              <button
                type="button"
                className="btn btn-primary text-xs mt-2"
                disabled={isReadOnly || triggering}
                onClick={handleRunNow}
              >
                {triggering ? (
                  <RefreshCw size={14} className="animate-spin mr-1" />
                ) : (
                  <Play size={14} className="mr-1" />
                )}
                {triggering ? "Queuing..." : "Run 3-Step Pipeline Now"}
              </button>
            </div>
            <div className="p-3 rounded-lg bg-blue-500/10 text-blue-500">
              <Play size={20} />
            </div>
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Execution History & Step Progress"
        actions={
          <button
            type="button"
            className="btn btn-outline text-xs inline-flex items-center gap-1"
            onClick={fetchRuns}
            disabled={loading}
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        }
      >
        {loading ? (
          <div className="p-8 text-center text-muted">Loading pipeline execution logs...</div>
        ) : runs.length === 0 ? (
          <div className="p-8 text-center text-muted border border-dashed rounded-lg">
            No pipeline executions logged yet. Runs executed by GitHub Actions, Airflow, CLI, or Portal UI will appear here.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b text-xs text-muted font-medium uppercase tracking-wider">
                  <th className="pb-3 px-3">Run ID</th>
                  <th className="pb-3 px-3">Trigger Source</th>
                  <th className="pb-3 px-3">Status</th>
                  <th className="pb-3 px-3">Step 1 (Raw 6W)</th>
                  <th className="pb-3 px-3">Step 2 (Baseline)</th>
                  <th className="pb-3 px-3">Step 3 (FF Hub)</th>
                  <th className="pb-3 px-3">Started At</th>
                  <th className="pb-3 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {runs.map((r) => (
                  <tr key={r.run_id} className="hover:bg-muted/50 transition-colors">
                    <td className="py-3 px-3 font-mono text-xs font-semibold">{r.run_id}</td>
                    <td className="py-3 px-3">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-secondary text-secondary-foreground">
                        {r.triggered_by}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      {renderStepBadge(r.status, r.status)}
                    </td>
                    <td className="py-3 px-3">{renderStepBadge(r.step1_status, "Step 1")}</td>
                    <td className="py-3 px-3">{renderStepBadge(r.step2_status, "Step 2")}</td>
                    <td className="py-3 px-3">{renderStepBadge(r.step3_status, "Step 3")}</td>
                    <td className="py-3 px-3 text-xs text-muted">
                      {new Date(r.started_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        type="button"
                        className="btn btn-ghost text-xs inline-flex items-center gap-1"
                        onClick={() => handleViewLog(r.run_id)}
                      >
                        <Terminal size={13} />
                        View Log
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {/* Log Console Modal / Panel */}
      {selectedRunId && (
        <SectionCard
          title={`Console Log Output — ${selectedRunId}`}
          actions={
            <button
              type="button"
              className="btn btn-ghost text-xs"
              onClick={() => {
                setSelectedRunId(null);
                setLogDetail(null);
              }}
            >
              Close
            </button>
          }
        >
          {loadingLog ? (
            <div className="p-6 text-center text-muted">Loading log details...</div>
          ) : logDetail ? (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-4 text-xs">
                <div>
                  <strong className="text-muted">Triggered By:</strong> {logDetail.triggered_by}
                </div>
                <div>
                  <strong className="text-muted">Started:</strong> {new Date(logDetail.started_at).toLocaleString()}
                </div>
                <div>
                  <strong className="text-muted">Completed:</strong>{" "}
                  {logDetail.completed_at ? new Date(logDetail.completed_at).toLocaleString() : "In progress"}
                </div>
              </div>

              <div className="bg-zinc-950 text-zinc-100 font-mono text-xs p-4 rounded-lg overflow-x-auto max-h-96 border border-zinc-800 space-y-1">
                {logDetail.console_log ? (
                  logDetail.console_log.split("\n").map((line, idx) => (
                    <div key={idx} className="whitespace-pre-wrap">
                      {line}
                    </div>
                  ))
                ) : (
                  <div className="text-zinc-500 italic">No output logged yet for this run.</div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-4 text-xs text-red-500">Failed to load log detail.</div>
          )}
        </SectionCard>
      )}
    </AppShell>
  );
}
