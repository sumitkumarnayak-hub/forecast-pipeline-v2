"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import api from "@/lib/api";
import { getUser, canWrite } from "@/lib/auth";
import { RefreshCw, Lock, DownloadCloud, Layers, Play, BarChart2 } from "lucide-react";

function fmt(dt: string | null) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export default function FinalPlanPage() {
  const user = getUser();
  const [status, setStatus] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState("");
  const [msg, setMsg] = useState({ text: "", type: "" });

  const load = async () => {
    setLoading(true);
    try {
      const [s, r, c] = await Promise.all([
        api.get("/api/final-plan/status"),
        api.get("/api/final-plan/runs"),
        api.get("/api/final-plan/config"),
      ]);
      setStatus(s.data); setRuns(r.data); setConfig(c.data);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const doSync = async (action: "adhoc" | "inventory") => {
    setSyncing(action); setMsg({ text: "", type: "" });
    try {
      const ep = action === "adhoc" ? "/api/final-plan/sync-adhoc" : "/api/final-plan/sync-inventory";
      const { data } = await api.post(ep);
      setMsg({ text: `✅ ${data.detail}`, type: "success" });
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Sync failed"}`, type: "danger" });
    }
    setSyncing("");
  };

  const notApproved = !status?.baseline_approved;

  const inputsTab = (
    <div className="grid-2">
      <div className="card">
        <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.4rem" }}>Sync Inputs</div>
        <div className="text-xs text-muted" style={{ marginBottom: "1rem" }}>
          Pull adhoc adjustment & inventory logic files from Google Sheets to local Excel.
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <button
            className="btn btn-secondary w-full"
            onClick={() => doSync("adhoc")}
            disabled={!!syncing || notApproved || !canWrite(user?.role)}
          >
            {syncing === "adhoc"
              ? <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
              : <DownloadCloud size={14} />}
            {" "}Sync Adhoc Adjustments
          </button>
          <button
            className="btn btn-secondary w-full"
            onClick={() => doSync("inventory")}
            disabled={!!syncing || notApproved || !canWrite(user?.role)}
          >
            {syncing === "inventory"
              ? <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
              : <Layers size={14} />}
            {" "}Sync Inventory Logic
          </button>
        </div>
      </div>

      {config && (
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>📂 Input Paths</div>
          {[
            ["FF Inputs Folder",  config.ff_inputs_folder],
            ["Inv Logic Folder",  config.ff_inv_logic_folder],
            ["Masters XLSX",      config.ff_masters_xlsx],
            ["Baseline Outputs",  config.baseline_outputs_folder],
          ].map(([k, v]) => (
            <div key={k as string} style={{ marginBottom: "0.6rem" }}>
              <div style={{ fontSize: "0.68rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "0.15rem" }}>{k}</div>
              <div style={{ fontSize: "0.7rem", fontFamily: "monospace", color: "var(--text-secondary)", wordBreak: "break-all", background: "var(--bg-elevated)", padding: "0.3rem 0.5rem", borderRadius: "var(--radius-sm)" }}>{v || "—"}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const runTab = (
    <div className="card">
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>▶ Run Final Plan</div>
      <div className="text-sm text-muted mb-4">Click below to trigger the final plan generator (for manual overrides). Auto-Pilot handles this automatically.</div>
      <button className="btn btn-primary" disabled={notApproved || !canWrite(user?.role)}>
        <Play size={14} /> Run Final Plan
      </button>
    </div>
  );

  const outputTab = (
    <div className="card">
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <BarChart2 size={16} /> Run History
      </div>
      {loading ? (
        <div style={{ textAlign: "center", padding: "2rem" }}><span className="spinner" /></div>
      ) : runs.length === 0 ? (
        <div className="text-xs text-muted">No final plan runs recorded yet.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run ID</th><th>Status</th><th>Date</th><th>Output</th><th>Validation</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r: any) => (
                <tr key={r.run_id}>
                  <td style={{ fontFamily: "monospace", fontSize: "0.68rem" }}>{r.run_id?.slice(-10) || "—"}</td>
                  <td>
                    <span className={`badge badge-${r.status === "completed" ? "green" : r.status === "failed" ? "red" : "yellow"}`}>
                      {r.status}
                    </span>
                  </td>
                  <td style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>{fmt(r.run_date)}</td>
                  <td style={{ fontSize: "0.7rem", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.output_file || "—"}
                  </td>
                  <td>
                    {r.validation_status ? (
                      <span className={`badge badge-${r.validation_status === "passed" ? "green" : "red"}`}>
                        {r.validation_status}
                      </span>
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  const mainTabs = [
    { id: "inputs", label: "📥 Inputs", content: inputsTab },
    { id: "run", label: "▶ Run", content: runTab },
    { id: "output", label: "📊 Output", content: outputTab },
  ];

  return (
    <AppShell
      title="Final Plan"
      subtitle="Sync inputs, generate and approve the final distribution plan"
      actions={
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {notApproved && (
        <div className="alert alert-warning" style={{ marginBottom: "1.25rem" }}>
          <Lock size={15} /> Baseline not yet approved. Final Plan is locked until an admin approves the baseline.
        </div>
      )}

      {msg.text && (
        <div className={`alert alert-${msg.type}`} style={{ marginBottom: "1rem" }}>{msg.text}</div>
      )}

      <Tabs tabs={mainTabs} defaultTab="inputs" />
    </AppShell>
  );
}
