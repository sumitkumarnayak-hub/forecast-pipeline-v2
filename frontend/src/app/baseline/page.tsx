"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import api from "@/lib/api";
import { getUser, canApprove } from "@/lib/auth";
import { CheckCircle, XCircle, RefreshCw, ThumbsUp, ThumbsDown, BarChart2, Play } from "lucide-react";

function fmt(dt: string | null) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export default function BaselinePage() {
  const user = getUser();
  const [status, setStatus] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [acting, setActing] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [s, r, c] = await Promise.all([
        api.get("/api/baseline/status"),
        api.get("/api/baseline/runs"),
        api.get("/api/baseline/config"),
      ]);
      setStatus(s.data); setRuns(r.data); setConfig(c.data);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const doApprove = async () => {
    setActing("approve");
    try {
      const { data } = await api.post("/api/baseline/approve");
      setMsg({ text: data.detail, type: "success" });
      load();
    } catch (e: any) {
      setMsg({ text: e?.response?.data?.detail || "Error", type: "danger" });
    }
    setActing("");
  };

  const doReject = async () => {
    setActing("reject");
    try {
      const { data } = await api.post("/api/baseline/reject");
      setMsg({ text: data.detail, type: "warning" });
      load();
    } catch (e: any) {
      setMsg({ text: e?.response?.data?.detail || "Error", type: "danger" });
    }
    setActing("");
  };

  const configAndRunTab = (
    <div className="card">
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>📂 Configuration & Output Paths</div>
      {config ? (
        <>
          {[
            ["Masters XLSX", config.ff_masters_xlsx],
            ["Raw Actuals", config.raw_actuals_folder],
            ["DP Logics", config.dp_logics_folder],
            ["Baseline Outputs", config.baseline_outputs_folder],
          ].map(([k, v]) => (
            <div key={k as string} style={{ marginBottom: "0.6rem" }}>
              <div className="text-xs" style={{ color: "var(--text-muted)", marginBottom: "0.1rem" }}>{k}</div>
              <div style={{ fontSize: "0.72rem", fontFamily: "monospace", color: "var(--text-secondary)", wordBreak: "break-all", background: "var(--bg-elevated)", padding: "0.3rem 0.5rem", borderRadius: "var(--radius-sm)" }}>{v || "—"}</div>
            </div>
          ))}
          {config.pipeline_params_sheet_url && (
            <a href={config.pipeline_params_sheet_url} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm" style={{ marginTop: "1rem" }}>
              🔗 Open Pipeline Params Sheet
            </a>
          )}
        </>
      ) : (
        <div className="text-xs text-muted">Loading config...</div>
      )}
      <div className="divider" />
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>▶ Run Manual Baseline</div>
      <div className="text-xs text-muted mb-3">For full orchestration, use the Auto-Pilot page instead.</div>
      <button className="btn btn-primary" disabled>
        <Play size={14} /> Run Baseline
      </button>
    </div>
  );

  const insightsAndLogsTab = (
    <div className="card">
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <BarChart2 size={16} /> Run History
      </div>
      {loading ? (
        <div style={{ textAlign: "center", padding: "2rem" }}><span className="spinner" /></div>
      ) : runs.length === 0 ? (
        <div className="text-xs text-muted">No baseline runs recorded yet.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Date</th>
                <th>Validation</th>
                <th>Approved By</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r: any) => (
                <tr key={r.run_id}>
                  <td style={{ fontFamily: "monospace", fontSize: "0.68rem" }}>{r.run_id?.slice(-10) || "—"}</td>
                  <td>{r.run_name || "—"}</td>
                  <td>
                    <span className={`badge badge-${r.status === "completed" ? "green" : r.status === "failed" ? "red" : "yellow"}`}>
                      {r.status}
                    </span>
                  </td>
                  <td style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>{fmt(r.run_date)}</td>
                  <td>
                    {r.validation_status ? (
                      <span className={`badge badge-${r.validation_status === "passed" ? "green" : "red"}`}>
                        {r.validation_status}
                      </span>
                    ) : "—"}
                  </td>
                  <td style={{ fontSize: "0.72rem" }}>{r.approved_by_name || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  const approvalTab = (
    <div className="card">
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.5rem" }}>✅ Baseline Approval</div>
      <div className="text-sm text-muted" style={{ marginBottom: "1.5rem" }}>
        Approve the latest baseline to unlock Final Plan for all planners.
      </div>
      
      {!loading && status && (
        <div className={`alert ${status.approved ? "alert-success" : "alert-warning"}`} style={{ marginBottom: "1.5rem" }}>
          {status.approved
            ? <><CheckCircle size={15} /> Baseline is <strong>approved</strong> — Final Plan is unlocked.</>
            : <><XCircle size={15} /> Baseline not yet approved. Admin must approve before Final Plan becomes available.</>}
        </div>
      )}

      {canApprove(user?.role) ? (
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button className="btn btn-success" onClick={doApprove} disabled={!!acting || status?.approved}>
            {acting === "approve" ? <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> : <ThumbsUp size={13} />}
            {" "}Approve
          </button>
          <button className="btn btn-danger" onClick={doReject} disabled={!!acting || !status?.approved}>
            {acting === "reject" ? <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> : <ThumbsDown size={13} />}
            {" "}Reject
          </button>
        </div>
      ) : (
        <div className="text-sm text-muted">You do not have permission to approve the baseline.</div>
      )}
    </div>
  );

  const mainTabs = [
    { id: "config", label: "🚀 Config & Run", content: configAndRunTab },
    { id: "insights", label: "📈 Insights & Logs", content: insightsAndLogsTab },
    { id: "approval", label: "✅ Approval", content: approvalTab },
  ];

  return (
    <AppShell
      title="Baseline Generation"
      subtitle="Run history, approval controls & configuration"
      actions={
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {msg.text && (
        <div className={`alert alert-${msg.type}`} style={{ marginBottom: "1.25rem" }}>
          {msg.text}
        </div>
      )}

      <Tabs tabs={mainTabs} defaultTab="config" />
    </AppShell>
  );
}
