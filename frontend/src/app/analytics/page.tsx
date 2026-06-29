"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import api from "@/lib/api";
import { RefreshCw, TrendingUp, AlertTriangle } from "lucide-react";

export default function AnalyticsPage() {
  const [avail, setAvail] = useState<{ rows: any[]; columns: string[] }>({ rows: [], columns: [] });
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [a, s] = await Promise.all([
        api.get("/api/insights/availability-loss"),
        api.get("/api/insights/6w-summary"),
      ]);
      setAvail(a.data);
      setSummary(s.data);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const availTab = (
    <div className="card">
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>
        Availability Loss Data — <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>Avail Led Rev Loss sheet</span>
      </div>
      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem" }}><span className="spinner" style={{ width: 28, height: 28 }} /></div>
      ) : avail.rows.length === 0 ? (
        <div className="alert alert-warning">
          <AlertTriangle size={14} /> No data found. Check AVAILABILITY_LOSS_SHEET_URL in your .env and ensure Google credentials are configured.
        </div>
      ) : (
        <div className="table-wrap" style={{ maxHeight: 520, overflowY: "auto" }}>
          <table>
            <thead><tr>{avail.columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {avail.rows.map((row, i) => (
                <tr key={i}>
                  {avail.columns.map(c => (
                    <td key={c} style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>{String(row[c] ?? "—")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  const sixWeekTab = (
    <div className="card">
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>6-Week Rolling Dataset</div>
      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem" }}><span className="spinner" style={{ width: 28, height: 28 }} /></div>
      ) : !summary?.available ? (
        <div className="alert alert-warning">
          <AlertTriangle size={14} />{" "}
          6w_v3.parquet not found in outputs/. Run the baseline Auto-Pilot to generate it, or copy the file from:
          <code style={{ display: "block", marginTop: "0.4rem", fontSize: "0.72rem", fontFamily: "monospace", background: "rgba(255,255,255,0.06)", padding: "0.25rem 0.5rem", borderRadius: 4 }}>
            outputs/6w_v3.parquet
          </code>
        </div>
      ) : (
        <>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
            <span className="badge badge-green">Available</span>
            <span className="badge badge-blue">{summary.columns?.length} columns</span>
          </div>
          <div style={{ fontWeight: 600, fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>Columns</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginBottom: "1rem" }}>
            {(summary.columns || []).map((c: string) => (
              <span key={c} style={{ fontSize: "0.7rem", background: "var(--bg-elevated)", border: "1px solid var(--border)", padding: "0.15rem 0.5rem", borderRadius: 4, color: "var(--text-secondary)", fontFamily: "monospace" }}>{c}</span>
            ))}
          </div>
          {summary.sample_rows?.length > 0 && (
            <>
              <div style={{ fontWeight: 600, fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>Sample Rows</div>
              <div className="table-wrap">
                <table>
                  <thead><tr>{summary.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
                  <tbody>
                    {summary.sample_rows.map((row: any, i: number) => (
                      <tr key={i}>{summary.columns.map((c: string) => <td key={c} style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>{String(row[c] ?? "—")}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );

  const mainTabs = [
    { id: "avail", label: "Availability Loss", content: availTab },
    { id: "6w", label: "6-Week Data", content: sixWeekTab },
  ];

  return (
    <AppShell
      title="Analytics"
      subtitle="Availability loss insights & 6-week rolling data"
      actions={
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {/* Stats */}
      <div className="stat-grid" style={{ marginBottom: "1.5rem" }}>
        <div className="stat-card">
          <div className="stat-label">Availability Loss Rows</div>
          <div className="stat-value" style={{ color: "var(--red)" }}>{loading ? "—" : avail.rows.length}</div>
          <div className="stat-sub">From Google Sheets</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">6W Parquet</div>
          <div className="stat-value" style={{ color: summary?.available ? "var(--green)" : "var(--text-muted)" }}>
            {loading ? "—" : summary?.available ? "Ready" : "Missing"}
          </div>
          <div className="stat-sub">{summary?.columns?.length ? `${summary.columns.length} columns` : "6w_v3.parquet"}</div>
        </div>
      </div>

      <Tabs tabs={mainTabs} defaultTab="avail" />
    </AppShell>
  );
}
