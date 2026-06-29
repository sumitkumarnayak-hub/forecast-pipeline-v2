"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import api from "@/lib/api";
import { getUser, canWrite } from "@/lib/auth";
import { RefreshCw, CheckCircle, XCircle, PauseCircle, Clock, AlertTriangle } from "lucide-react";

const STATUS_ICON: Record<string, JSX.Element> = {
  passed:    <CheckCircle size={14} color="var(--green)" />,
  completed: <CheckCircle size={14} color="var(--green)" />,
  failed:    <XCircle size={14} color="var(--red)" />,
  manual:    <PauseCircle size={14} color="var(--yellow)" />,
  partial:   <AlertTriangle size={14} color="var(--yellow)" />,
  running:   <RefreshCw size={14} color="var(--blue)" className="animate-spin" />,
  pending:   <Clock size={14} color="var(--text-muted)" />,
};

const STATUS_CLASS: Record<string, string> = {
  passed: "passed", completed: "passed", failed: "failed",
  manual: "manual", partial: "manual", running: "running",
};

function fmt(dt: string | null) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export default function DashboardPage() {
  const user = getUser();
  const [flow, setFlow] = useState<any>(null);
  const [baselineRuns, setBaselineRuns] = useState<any[]>([]);
  const [emailLog, setEmailLog] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [f, br, el] = await Promise.all([
        api.get("/api/dashboard/pipeline-flow"),
        api.get("/api/dashboard/baseline-runs"),
        api.get("/api/dashboard/email-log"),
      ]);
      setFlow(f.data); setBaselineRuns(br.data); setEmailLog(el.data);
    } catch { }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const runAudit = async () => {
    setRunning(true); setMsg("");
    try {
      const { data } = await api.post("/api/dashboard/pipeline-flow/run");
      setMsg(`✅ Audit complete — run ID: ${data.run_id}`);
      load();
    } catch (e: any) { setMsg("❌ " + (e?.response?.data?.detail || "Audit failed")); }
    setRunning(false);
  };

  const passed = flow?.steps?.filter((s: any) => s.status === "passed").length || 0;
  const failed = flow?.steps?.filter((s: any) => s.status === "failed").length || 0;
  const manual = flow?.steps?.filter((s: any) => s.status === "manual").length || 0;
  const total  = flow?.steps?.length || 7;

  return (
    <AppShell
      title="Dashboard"
      subtitle="Weekly pipeline flow & run history"
      actions={
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {/* Stats row */}
      <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
        {[
          { label: "Steps Passed",  value: loading ? "—" : `${passed}/${total}`, color: "var(--green)", sub: "Pipeline checks" },
          { label: "Steps Failed",  value: loading ? "—" : failed, color: failed > 0 ? "var(--red)" : "var(--text-muted)", sub: "Need attention" },
          { label: "Awaiting Action", value: loading ? "—" : manual, color: manual > 0 ? "var(--yellow)" : "var(--text-muted)", sub: "Manual steps" },
          { label: "Baseline Runs", value: baselineRuns.length, color: "var(--blue)", sub: "Last 10 runs" },
        ].map(s => (
          <div className="stat-card" key={s.label}>
            <div className="stat-label">{s.label}</div>
            <div className="stat-value" style={{ color: s.color }}>{s.value}</div>
            <div className="stat-sub">{s.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
        {/* Pipeline flow */}
        <div className="card">
          <div className="flex items-center justify-between" style={{ marginBottom: "1rem" }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>Pipeline Flow</div>
              <div className="text-xs text-muted">Live step evaluation</div>
            </div>
            {canWrite(user?.role) && (
              <button className="btn btn-primary btn-sm" onClick={runAudit} disabled={running}>
                {running ? <span className="spinner" style={{ width: 11, height: 11, borderWidth: 2 }} /> : <RefreshCw size={12} />}
                {running ? " Running…" : " Run Audit"}
              </button>
            )}
          </div>

          {msg && <div className={`alert ${msg.startsWith("✅") ? "alert-success" : "alert-danger"}`} style={{ marginBottom: "0.75rem", fontSize: "0.75rem" }}>{msg}</div>}

          {loading ? (
            <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
              <span className="spinner" style={{ width: 20, height: 20 }} />
            </div>
          ) : (
            <div className="step-list">
              {(flow?.steps || []).map((step: any, i: number) => (
                <div key={step.step_key} className={`step-item ${STATUS_CLASS[step.status] || ""}`}>
                  <div className={`step-icon ${STATUS_CLASS[step.status] || "pending"}`}>
                    {step.step_order}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="step-label">{step.step_name}</div>
                    <div className="step-message">{step.message}</div>
                    {step.error_detail && <div className="step-detail">↳ {step.error_detail}</div>}
                  </div>
                  {STATUS_ICON[step.status] || <Clock size={14} color="var(--text-muted)" />}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right column */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Baseline runs */}
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>Recent Baseline Runs</div>
            {baselineRuns.length === 0 ? (
              <div className="text-xs text-muted">No baseline runs yet.</div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Run ID</th><th>Status</th><th>Date</th><th>Validation</th></tr></thead>
                  <tbody>
                    {baselineRuns.slice(0, 6).map((r: any) => (
                      <tr key={r.run_id}>
                        <td style={{ fontFamily: "monospace", fontSize: "0.7rem" }}>{r.run_id?.slice(-8)}</td>
                        <td>
                          <span className={`badge badge-${r.status === "completed" ? "green" : r.status === "failed" ? "red" : "yellow"}`}>
                            {r.status}
                          </span>
                        </td>
                        <td style={{ fontSize: "0.72rem" }}>{fmt(r.run_date)}</td>
                        <td>
                          {r.validation_status && (
                            <span className={`badge badge-${r.validation_status === "passed" ? "green" : "red"}`}>
                              {r.validation_status}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Email log */}
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>Email Notifications</div>
            {emailLog.length === 0 ? (
              <div className="text-xs text-muted">No emails sent yet.</div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Type</th><th>Status</th><th>Sent At</th></tr></thead>
                  <tbody>
                    {emailLog.slice(0, 5).map((e: any) => (
                      <tr key={e.id}>
                        <td style={{ fontSize: "0.72rem" }}>{e.email_type || "—"}</td>
                        <td><span className={`badge badge-${e.status === "sent" ? "green" : "red"}`}>{e.status}</span></td>
                        <td style={{ fontSize: "0.72rem" }}>{fmt(e.sent_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
