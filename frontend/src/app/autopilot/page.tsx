"use client";
import { useEffect, useRef, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import api from "@/lib/api";
import { getUser, canWrite } from "@/lib/auth";
import { Zap, CheckCircle, XCircle, Loader2, RefreshCw, FolderOpen, MousePointer2 } from "lucide-react";
import Link from "next/link";

const STEP_LABELS = [
  { key: "master_sync",    label: "Master Data Sync & Validation",    desc: "Sync Product Masters from Google Sheets → Excel" },
  { key: "new_hub_launch", label: "New Hub Launch (P-H Master)",       desc: "Clone P-H Master rows for new hub configs" },
  { key: "pull_raw_data",  label: "Pull Raw Data",                     desc: "Fetch RDS/Trino actuals → parquet" },
  { key: "sync_config",    label: "Sync Config Parameters",            desc: "Download DP Logics workbooks & parquet sidecars" },
  { key: "run_engine",     label: "Run Baseline Engine",               desc: "Generate Summary_*.xlsx baseline output" },
  { key: "notify",         label: "Email Notification",                desc: "Send success/failure email to recipients" },
];

interface StepResult {
  index: number;
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  message: string;
  error?: string;
}

export default function AutopilotPage() {
  const user = getUser();
  const [steps, setSteps] = useState<StepResult[]>(
    STEP_LABELS.map((s, i) => ({ index: i, key: s.key, label: s.label, status: "pending", message: "" }))
  );
  const [taskId, setTaskId] = useState<string | null>(null);
  const [globalStatus, setGlobalStatus] = useState<"idle" | "running" | "completed" | "failed">("idle");
  const [fromStep, setFromStep] = useState(0);
  const [paths, setPaths] = useState<any>(null);
  const [state, setState] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    api.get("/api/autopilot/output-paths").then(r => setPaths(r.data)).catch(() => {});
    api.get("/api/autopilot/state").then(r => setState(r.data)).catch(() => {});
  }, []);

  const resetSteps = () =>
    setSteps(STEP_LABELS.map((s, i) => ({ index: i, key: s.key, label: s.label, status: "pending", message: "" })));

  const startRun = async () => {
    resetSteps();
    setGlobalStatus("running");
    setMsg("");
    try {
      const token = localStorage.getItem("ps_token");
      const { data } = await api.post(`/api/autopilot/run?from_step=${fromStep}`);
      setTaskId(data.task_id);

      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const es = new EventSource(`${API_BASE}/api/autopilot/stream/${data.task_id}`);
      esRef.current = es;

      es.onmessage = (e) => {
        const payload = JSON.parse(e.data);
        if (payload.event === "step") {
          setSteps(prev => {
            const next = [...prev];
            // Mark previous steps as completed if we jump ahead
            for (let i = 0; i < payload.index; i++) {
              if (next[i].status === "pending") next[i] = { ...next[i], status: "completed", message: "Done" };
            }
            next[payload.index] = {
              index: payload.index,
              key: payload.key,
              label: payload.label || STEP_LABELS[payload.index]?.label || payload.key,
              status: payload.status as any,
              message: payload.message || "",
              error: payload.error,
            };
            return next;
          });
        } else if (payload.event === "completed") {
          setGlobalStatus("completed");
          setMsg("✅ All 6 steps completed successfully.");
          es.close();
        } else if (payload.event === "failed") {
          setGlobalStatus("failed");
          setMsg(`❌ Pipeline failed: ${payload.error || "Unknown error"}`);
          es.close();
        }
      };
      es.onerror = () => {
        setGlobalStatus("failed");
        setMsg("❌ Connection lost. Check backend logs.");
        es.close();
      };
    } catch (e: any) {
      setGlobalStatus("failed");
      setMsg("❌ " + (e?.response?.data?.detail || "Failed to start"));
    }
  };

  const stepStatusIcon = (s: StepResult) => {
    if (s.status === "completed") return <CheckCircle size={18} color="var(--green)" />;
    if (s.status === "failed")    return <XCircle size={18} color="var(--red)" />;
    if (s.status === "running")   return <Loader2 size={18} color="var(--blue)" className="animate-spin" />;
    return <div style={{ width: 18, height: 18, borderRadius: "50%", border: "2px solid var(--border)", background: "var(--bg-elevated)" }} />;
  };

  const autoPilotTab = (
    <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: "1.25rem" }}>
      {/* Steps panel */}
      <div className="card">
        <div className="flex items-center justify-between" style={{ marginBottom: "1.25rem" }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: "0.95rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Zap size={16} color="var(--blue)" /> Auto-Pilot Steps
            </div>
            <div className="text-xs text-muted" style={{ marginTop: "0.2rem" }}>
              Runs all 6 steps sequentially. Failures stop the pipeline.
            </div>
          </div>
        </div>

        {/* Start controls */}
        {canWrite(user?.role) && (
          <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", marginBottom: "1.25rem" }}>
            <div>
              <label className="form-label" style={{ marginBottom: "0.25rem" }}>Resume from step</label>
              <select
                className="form-input"
                value={fromStep}
                onChange={e => setFromStep(Number(e.target.value))}
                disabled={globalStatus === "running"}
                style={{ width: 180 }}
              >
                {STEP_LABELS.map((s, i) => (
                  <option key={s.key} value={i}>Step {i + 1}: {s.label.split(" ").slice(0, 3).join(" ")}</option>
                ))}
              </select>
            </div>
            <button
              className={`btn btn-primary btn-lg`}
              onClick={startRun}
              disabled={globalStatus === "running" || !canWrite(user?.role)}
              style={{ marginTop: "1.3rem" }}
            >
              {globalStatus === "running"
                ? <><Loader2 size={14} className="animate-spin" /> Running…</>
                : <><Zap size={14} /> {fromStep > 0 ? `Resume from Step ${fromStep + 1}` : "Run Auto-Pilot"}</>}
            </button>
            {globalStatus !== "running" && globalStatus !== "idle" && (
              <button className="btn btn-secondary btn-sm" onClick={resetSteps} style={{ marginTop: "1.3rem" }}>
                <RefreshCw size={12} /> Reset
              </button>
            )}
          </div>
        )}

        {/* Message */}
        {msg && (
          <div className={`alert ${msg.startsWith("✅") ? "alert-success" : "alert-danger"}`} style={{ marginBottom: "1rem", fontSize: "0.8rem" }}>
            {msg}
          </div>
        )}

        {/* Steps */}
        <div>
          {steps.map((step, i) => (
            <div key={step.key} className={`autopilot-step ${step.status}`}>
              <div className={`step-number ${step.status}`}>{i + 1}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text-primary)" }}>
                  {STEP_LABELS[i]?.label || step.label}
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.1rem" }}>
                  {STEP_LABELS[i]?.desc}
                </div>
                {step.message && (
                  <div style={{ fontSize: "0.75rem", color: step.status === "failed" ? "var(--red)" : "var(--text-secondary)", marginTop: "0.25rem" }}>
                    {step.message}
                  </div>
                )}
                {step.error && (
                  <div style={{ fontSize: "0.72rem", color: "var(--red)", marginTop: "0.15rem", fontFamily: "monospace" }}>
                    ↳ {step.error}
                  </div>
                )}
              </div>
              {stepStatusIcon(step)}
            </div>
          ))}
        </div>
      </div>

      {/* Right: output paths + last state */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        {paths && (
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <FolderOpen size={15} /> Output Paths
            </div>
            {[
              ["Masters XLSX", paths.ff_masters_xlsx],
              ["Raw Actuals", paths.raw_actuals_folder],
              ["DP Logics", paths.dp_logics_folder],
              ["Baseline Outputs", paths.baseline_outputs_folder],
            ].map(([k, v]) => (
              <div key={k as string} style={{ marginBottom: "0.7rem" }}>
                <div style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.15rem" }}>{k}</div>
                <div style={{ fontSize: "0.7rem", fontFamily: "monospace", color: "var(--text-secondary)", wordBreak: "break-all", background: "var(--bg-elevated)", padding: "0.3rem 0.5rem", borderRadius: "var(--radius-sm)" }}>{v || "—"}</div>
              </div>
            ))}
            {paths.pipeline_params_sheet_url && (
              <a href={paths.pipeline_params_sheet_url} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm w-full" style={{ marginTop: "0.25rem" }}>
                🔗 Pipeline Params Sheet
              </a>
            )}
          </div>
        )}

        {state && Object.keys(state).length > 0 && (
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>Last Run State</div>
            <pre style={{ fontSize: "0.7rem", color: "var(--text-secondary)", overflowX: "auto", whiteSpace: "pre-wrap" }}>
              {JSON.stringify(state, null, 2)}
            </pre>
          </div>
        )}

        <div className="card" style={{ background: "var(--blue-dim)", borderColor: "var(--border-accent)" }}>
          <div style={{ fontWeight: 700, fontSize: "0.85rem", marginBottom: "0.5rem", color: "var(--blue)" }}>💡 CLI Alternative</div>
          <div className="text-xs text-muted" style={{ lineHeight: 1.7 }}>
            Run from terminal (task-scheduler friendly):
            <pre style={{ marginTop: "0.4rem", color: "var(--text-secondary)", fontSize: "0.68rem", fontFamily: "monospace" }}>
{`python scripts/run_optimized_autopilot.py
python scripts/run_optimized_autopilot.py --from-step 2`}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );

  const manualWorkflowTab = (
    <div className="card" style={{ textAlign: "center", padding: "4rem 2rem", color: "var(--text-muted)" }}>
      <MousePointer2 size={48} style={{ opacity: 0.2, margin: "0 auto 1rem" }} />
      <div style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "0.5rem" }}>Manual Workflow</div>
      <div className="text-sm mb-4">You can execute the pipeline manually step-by-step using the sidebar navigation.</div>
      <div style={{ display: "flex", gap: "0.5rem", justifyContent: "center" }}>
        <Link href="/master-data" className="btn btn-secondary">Go to Master Data</Link>
        <Link href="/baseline" className="btn btn-secondary">Go to Baseline</Link>
      </div>
    </div>
  );

  const mainTabs = [
    { id: "pilot", label: "Auto-Pilot", content: autoPilotTab },
    { id: "manual", label: "Manual workflow", content: manualWorkflowTab },
  ];

  return (
    <AppShell
      title="Auto-Pilot"
      subtitle="6-step automated baseline pipeline with real-time progress"
    >
      <Tabs tabs={mainTabs} defaultTab="pilot" />
    </AppShell>
  );
}
