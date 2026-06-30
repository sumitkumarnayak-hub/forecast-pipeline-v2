"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import BaselineStepShell from "@/components/baseline/BaselineStepShell";
import SectionCard from "@/components/baseline/SectionCard";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { Play, RefreshCw } from "lucide-react";

function fmt(dt: string | null) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function GenerateContent() {
  const { readOnly } = useAuth();
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [fetchingPrev, setFetchingPrev] = useState(false);
  const [prevPreview, setPrevPreview] = useState<Record<string, unknown> | null>(null);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [ctx, setCtx] = useState<Record<string, unknown> | null>(null);
  const [runs, setRuns] = useState<Record<string, unknown>[]>([]);
  const [targetWeek, setTargetWeek] = useState(28);
  const [targetYear, setTargetYear] = useState(2026);
  const [demoFilter, setDemoFilter] = useState<{ active?: boolean; city?: string; hubs?: string[] } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, r] = await Promise.all([
        api.get("/api/baseline/generate/context"),
        api.get("/api/baseline/runs"),
      ]);
      setCtx(c.data);
      setRuns(r.data || []);
      setTargetWeek(Number(c.data.target_week) || 28);
      setTargetYear(Number(c.data.target_year) || 2026);
      setMsg({ text: "", type: "" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Failed to load", type: "danger" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    api.get("/api/demo-filter").then(r => setDemoFilter(r.data)).catch(() => {});
  }, [load]);

  const fetchPrevious = async () => {
    setFetchingPrev(true);
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/baseline/generate/fetch-previous-baseline", {
        target_week: targetWeek,
        target_year: targetYear,
      });
      setPrevPreview(data);
      setMsg({
        text: `Previous baseline loaded — ${Number(data.rows || 0).toLocaleString()} rows, BasePlan sum ${Number(data.base_plan_sum || 0).toLocaleString()}`,
        type: "success",
      });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Fetch previous failed", type: "danger" });
      setPrevPreview(null);
    } finally {
      setFetchingPrev(false);
    }
  };

  const runBaseline = async () => {
    setRunning(true);
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/baseline/generate/run", {
        target_week: targetWeek,
        target_year: targetYear,
      });
      setMsg({ text: data.detail + (data.output_file ? ` → ${data.output_file}` : ""), type: "success" });
      await load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Run failed", type: "danger" });
    } finally {
      setRunning(false);
    }
  };

  const active = ctx?.active_dataset as Record<string, unknown> | undefined;
  const summaries = (ctx?.summaries as { name: string; modified: string }[]) || [];
  const preflight = ctx?.preflight as {
    checks?: { id: string; label: string; ok: boolean; detail: string }[];
    ready?: boolean;
  } | undefined;

  return (
    <BaselineStepShell
      stepId="generate"
      actions={
        <button type="button" className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {readOnly && (
        <div className="alert alert-info text-sm mb-4">Read-only — baseline runs disabled.</div>
      )}
      {msg.text && <div className={`alert alert-${msg.type} mb-4`}>{msg.text}</div>}

      {demoFilter?.active && (
        <div className="alert alert-info text-sm mb-4">
          <strong>Demo mode active</strong>
          {demoFilter.city && demoFilter.city !== "All Cities" && <> — City: {demoFilter.city}</>}
          {demoFilter.hubs && demoFilter.hubs.length > 0 && <> — Hubs: {demoFilter.hubs.join(", ")}</>}
          . Baseline will run on the filtered dataset only.
        </div>
      )}

      {!active?.exists && (
        <div className="alert alert-warning text-sm mb-4">
          No active dataset — complete steps 1–2 first.
        </div>
      )}

      <SectionCard title="Week Configuration">
        <div className="grid-2" style={{ maxWidth: 400 }}>
          <div className="form-group">
            <label className="form-label">Target ISO Week</label>
            <input
              type="number"
              className="form-input"
              value={targetWeek}
              onChange={e => setTargetWeek(Number(e.target.value))}
              disabled={readOnly}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Target Year</label>
            <input
              type="number"
              className="form-input"
              value={targetYear}
              onChange={e => setTargetYear(Number(e.target.value))}
              disabled={readOnly}
            />
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Active Dataset">
        {active?.exists ? (
          <p className="text-sm">
            <strong>{Number(active.rows || 0).toLocaleString()} rows</strong>
            {Array.isArray(active.weeks) && (active.weeks as number[]).length > 0 && (
              <> · Weeks: {(active.weeks as number[]).map(w => `Wk ${w}`).join(", ")}</>
            )}
          </p>
        ) : (
          <p className="text-sm text-muted">Not loaded</p>
        )}
      </SectionCard>

      <SectionCard title="Previous Baseline (RDS)">
        <p className="text-xs text-muted mb-3">
          Fetches prior-week BasePlan from RDS cache into <code>prev_baseline_latest.parquet</code> for the engine.
        </p>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={readOnly || fetchingPrev}
          onClick={fetchPrevious}
        >
          {fetchingPrev ? (
            <span className="spinner" style={{ width: 14, height: 14 }} />
          ) : (
            <RefreshCw size={14} />
          )}
          {fetchingPrev ? "Fetching…" : "Fetch Previous Baseline"}
        </button>
        {Array.isArray(prevPreview?.preview_rows) && (
          <div className="table-wrap mt-4" style={{ maxHeight: 280, overflow: "auto" }}>
            <table>
              <thead>
                <tr>
                  {((prevPreview.columns as string[]) || Object.keys((prevPreview.preview_rows as Record<string, unknown>[])[0] || {})).map(c => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(prevPreview.preview_rows as Record<string, unknown>[]).slice(0, 20).map((row, i) => (
                  <tr key={i}>
                    {((prevPreview.columns as string[]) || Object.keys(row)).map(c => (
                      <td key={c} style={{ fontSize: "0.72rem" }}>
                        {String(row[c] ?? "—")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Pre-run Validation">
        {!preflight?.checks?.length ? (
          <p className="text-sm text-muted">Loading checklist…</p>
        ) : (
          <>
            <ul className="text-sm mb-3" style={{ paddingLeft: 0, listStyle: "none" }}>
              {preflight.checks.map(c => (
                <li key={c.id} className="mb-2 flex gap-2">
                  <span>{c.ok ? "✅" : "❌"}</span>
                  <span>
                    <strong>{c.label}</strong>
                    <span className="text-muted"> — {c.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
            {!preflight.ready && (
              <div className="alert alert-warning text-sm">
                Resolve failed checks in earlier baseline steps before running the engine.
              </div>
            )}
          </>
        )}
      </SectionCard>

      <SectionCard title="Run Baseline">
        <p className="text-xs text-muted mb-3">
          Runs <code>optimized_baseline_avail_correction.py</code> and writes Summary_*.xlsx.
        </p>
        <button
          type="button"
          className="btn btn-primary"
          disabled={readOnly || running || !active?.exists || preflight?.ready === false}
          onClick={runBaseline}
        >
          {running ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Play size={14} />}
          {running ? "Running… (may take several minutes)" : "Run Baseline & Save Summary"}
        </button>
      </SectionCard>

      {summaries.length > 0 && (
        <SectionCard title="Existing Summaries">
          <ul className="text-sm text-muted" style={{ paddingLeft: "1.25rem" }}>
            {summaries.slice(0, 10).map(s => (
              <li key={s.name}>
                {s.name} — {fmt(s.modified)}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      <SectionCard title="Recent Runs">
        {loading ? (
          <span className="spinner" />
        ) : runs.length === 0 ? (
          <p className="text-sm text-muted">No runs yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {runs.slice(0, 10).map(r => (
                  <tr key={String(r.run_id)}>
                    <td style={{ fontFamily: "monospace", fontSize: "0.68rem" }}>{String(r.run_id)}</td>
                    <td>{String(r.status)}</td>
                    <td style={{ fontSize: "0.72rem" }}>{fmt(r.run_date as string | null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>
    </BaselineStepShell>
  );
}

export default function GeneratePage() {
  return (
    <Suspense>
      <GenerateContent />
    </Suspense>
  );
}
