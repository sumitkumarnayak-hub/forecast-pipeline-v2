"use client";

import { Suspense, useCallback, useEffect, useState, type CSSProperties } from "react";
import { useSearchParams } from "next/navigation";
import BaselineStepShell from "@/components/baseline/BaselineStepShell";
import SectionCard from "@/components/baseline/SectionCard";
import { UrlTabs } from "@/components/ui/UrlTabs";
import { PAGE_TAB_TREES } from "@/lib/navigation";
import api from "@/lib/api";
import { RefreshCw, ShieldCheck } from "lucide-react";

interface ComparisonData {
  view: string;
  current_file?: string;
  previous_file?: string;
  columns?: string[];
  rows?: Record<string, unknown>[];
  row_count?: number;
}

type Thresholds = {
  negStrong: number;
  negMod: number;
  posMod: number;
  posStrong: number;
};

const DEFAULT_THRESHOLDS: Thresholds = {
  negStrong: -20,
  negMod: -10,
  posMod: 10,
  posStrong: 20,
};

function deltaStyle(val: unknown, t: Thresholds): CSSProperties {
  const n = typeof val === "number" ? val : parseFloat(String(val));
  if (Number.isNaN(n)) return {};
  if (n <= t.negStrong) return { background: "rgba(239,68,68,0.15)" };
  if (n <= t.negMod) return { background: "rgba(249,115,22,0.15)" };
  if (n >= t.posStrong) return { background: "rgba(34,197,94,0.15)" };
  if (n >= t.posMod) return { background: "rgba(245,158,11,0.15)" };
  return {};
}

function ComparisonPanel({ view }: { view: string }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ComparisonData | null>(null);
  const [msg, setMsg] = useState("");
  const [thresholds, setThresholds] = useState(DEFAULT_THRESHOLDS);
  const [dimFilter, setDimFilter] = useState("All");

  const load = useCallback(
    async (refresh = false) => {
      setLoading(true);
      setMsg("");
      try {
        const { data: res } = await api.get("/api/baseline/review/comparison", {
          params: { view, refresh },
        });
        setData(res);
        setDimFilter("All");
      } catch (e: unknown) {
        const err = e as { response?: { data?: { detail?: string } } };
        setMsg(err?.response?.data?.detail || "Failed to load comparison");
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [view],
  );

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <span className="spinner" />;
  if (msg) return <div className="alert alert-warning text-sm">{msg}</div>;
  if (!data?.rows?.length) return <p className="text-sm text-muted">No comparison rows for this view.</p>;

  const cols = data.columns || Object.keys(data.rows[0]);
  const dimCol = cols.find(c => !["Previous Baseline", "Current Baseline", "Delta %"].includes(c)) || cols[0];
  const dimValues = ["All", ...Array.from(new Set(data.rows.map(r => String(r[dimCol] ?? "")))).filter(Boolean).sort()];
  const filtered =
    dimFilter === "All" ? data.rows : data.rows.filter(r => String(r[dimCol]) === dimFilter);

  const prevTot = filtered.reduce((s, r) => s + Number(r["Previous Baseline"] || 0), 0);
  const currTot = filtered.reduce((s, r) => s + Number(r["Current Baseline"] || 0), 0);
  const pctTot = prevTot ? Math.round(((currTot - prevTot) / prevTot) * 1000) / 10 : 0;

  const downloadCsv = () => {
    const header = cols.join(",");
    const lines = filtered.map(r => cols.map(c => JSON.stringify(r[c] ?? "")).join(","));
    const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `comparison-${view}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <details className="mb-3">
        <summary className="text-sm font-semibold cursor-pointer">Configure change thresholds</summary>
        <div className="grid-4 gap-2 mt-2">
          {(
            [
              ["negStrong", "Strong ↓ %", -20],
              ["negMod", "Moderate ↓ %", -10],
              ["posMod", "Moderate ↑ %", 10],
              ["posStrong", "Strong ↑ %", 20],
            ] as const
          ).map(([key, label, def]) => (
            <label key={key} className="text-xs">
              {label}
              <input
                type="number"
                className="form-input text-sm w-full mt-1"
                value={thresholds[key]}
                onChange={e => setThresholds(t => ({ ...t, [key]: Number(e.target.value) }))}
              />
            </label>
          ))}
        </div>
      </details>

      {(data.current_file || data.previous_file) && (
        <p className="text-xs text-muted mb-3">
          Current: <strong>{data.current_file || "—"}</strong>
          {" · "}
          Previous: <strong>{data.previous_file || "—"}</strong>
          {" · "}
          {filtered.length} rows
        </p>
      )}

      <div className="stat-grid grid-3 mb-3">
        <div className="stat-card">
          <div className="stat-label">Previous total</div>
          <div className="stat-value">{prevTot.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Current total</div>
          <div className="stat-value">{currTot.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Overall delta %</div>
          <div className="stat-value">{pctTot >= 0 ? "+" : ""}{pctTot}%</div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-3 items-center">
        <label className="text-xs">
          Filter {dimCol}:{" "}
          <select className="form-input text-sm" value={dimFilter} onChange={e => setDimFilter(e.target.value)}>
            {dimValues.map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn-secondary btn-sm" onClick={downloadCsv}>Download CSV</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => load(true)}>
          <RefreshCw size={13} /> Rebuild cache
        </button>
      </div>

      <div className="table-wrap" style={{ maxHeight: 480, overflow: "auto" }}>
        <table>
          <thead>
            <tr>
              {cols.map(c => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((row, i) => (
              <tr key={i}>
                {cols.map(c => (
                  <td
                    key={c}
                    style={{
                      fontSize: "0.72rem",
                      whiteSpace: "nowrap",
                      ...(c === "Delta %" ? deltaStyle(row[c], thresholds) : {}),
                    }}
                  >
                    {String(row[c] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function HubSkuComparisonPanel() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ComparisonData & { metrics?: Record<string, number>; sheet_write?: Record<string, unknown> } | null>(null);
  const [msg, setMsg] = useState("");

  const load = async (refresh = true, writeSheet = false) => {
    setLoading(true);
    setMsg("");
    try {
      const { data: res } = await api.get("/api/baseline/review/hub-sku-comparison", {
        params: { refresh, write_sheet: writeSheet },
      });
      setData(res);
      if (writeSheet && res.sheet_write?.success) {
        setMsg("Comparison written to Baseline tab in Google Sheet.");
      } else if (writeSheet && res.sheet_write?.error) {
        setMsg(`Sheet write failed: ${res.sheet_write.error}`);
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg(err?.response?.data?.detail || "Failed to load comparison");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const m = data?.metrics;
  const cols = data?.columns || [];
  const rows = data?.rows || [];

  return (
    <>
      <p className="text-xs text-muted mb-3">Hub × SKU Class Prod × Day — previous vs current baseline.</p>
      <div className="flex flex-wrap gap-2 mb-3">
        <button type="button" className="btn btn-primary btn-sm" onClick={() => load(true, true)} disabled={loading}>
          {loading ? "Loading…" : "Load comparison (+ write to sheet)"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => load(false, false)} disabled={loading}>
          Show cached
        </button>
      </div>
      {msg && <div className="alert alert-info text-sm mb-3">{msg}</div>}
      {m && (
        <div className="stat-grid grid-3 mb-3">
          <div className="stat-card">
            <div className="stat-label">Previous total</div>
            <div className="stat-value">{m.previous_total?.toLocaleString()}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Current total</div>
            <div className="stat-value">{m.current_total?.toLocaleString()}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Overall delta %</div>
            <div className="stat-value">{m.overall_delta_pct >= 0 ? "+" : ""}{m.overall_delta_pct}%</div>
          </div>
        </div>
      )}
      {rows.length > 0 && (
        <div className="table-wrap" style={{ maxHeight: 400, overflow: "auto" }}>
          <table>
            <thead>
              <tr>{cols.map(c => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {rows.slice(0, 500).map((row, i) => (
                <tr key={i}>
                  {cols.map(c => (
                    <td key={c} style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>{String(row[c] ?? "—")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 500 && <p className="text-xs text-muted mt-2">Showing first 500 of {rows.length} rows.</p>}
        </div>
      )}
    </>
  );
}

function ReviewContent() {
  const searchParams = useSearchParams();
  const activeView = searchParams.get("view") || "city-day";
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<{
    available: boolean;
    file?: string;
    columns?: string[];
    rows?: Record<string, unknown>[];
  } | null>(null);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [validating, setValidating] = useState("");
  const [baselineValidation, setBaselineValidation] = useState<Record<string, unknown> | null>(null);
  const [masterValidation, setMasterValidation] = useState<Record<string, unknown> | null>(null);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/baseline/review/latest-summary?limit=200");
      setSummary(data);
      setMsg({ text: "", type: "" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Failed to load summary", type: "danger" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const validateLatestBaseline = async () => {
    setValidating("baseline");
    try {
      const { data } = await api.get("/api/validation/validate-latest/baseline");
      setBaselineValidation(data.validation as Record<string, unknown>);
      setMsg({ text: `Validated ${data.file}`, type: "success" });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Baseline validation failed", type: "danger" });
      setBaselineValidation(null);
    } finally {
      setValidating("");
    }
  };

  const validateMasters = async () => {
    setValidating("master");
    try {
      const { data } = await api.post("/api/validation/validate-master");
      setMasterValidation(data);
      setMsg({
        text: data.valid ? "Master data validation passed" : `${data.error_count} validation issue(s)`,
        type: data.valid ? "success" : "warning",
      });
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Master validation failed", type: "danger" });
      setMasterValidation(null);
    } finally {
      setValidating("");
    }
  };

  const comparisonTabs = PAGE_TAB_TREES.reviewBaseline.top.map(t => ({
    id: t.id,
    label: t.label,
    content: <ComparisonPanel view={t.id} key={t.id} />,
  }));

  return (
    <BaselineStepShell
      stepId="review"
      actions={
        <button type="button" className="btn btn-secondary btn-sm" onClick={loadSummary} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {msg.text && <div className={`alert alert-${msg.type} mb-4`}>{msg.text}</div>}

      <SectionCard title="Output Validation (Pandera)">
        <p className="text-xs text-muted mb-3">
          Validate the latest Summary file on disk and re-run P-H master rules before approval.
        </p>
        <div className="flex flex-wrap gap-2 mb-3">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={validateLatestBaseline}
            disabled={!!validating}
          >
            <ShieldCheck size={13} /> Validate latest baseline
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={validateMasters}
            disabled={!!validating}
          >
            <ShieldCheck size={13} /> Validate master data
          </button>
        </div>
        {baselineValidation && (
          <div className={`alert alert-${baselineValidation.valid ? "success" : "warning"} text-sm mb-2`}>
            Baseline schema: {baselineValidation.valid ? "passed" : "issues found"}
            {Array.isArray(baselineValidation.errors) && baselineValidation.errors.length > 0 && (
              <ul className="mt-2 pl-4">
                {(baselineValidation.errors as string[]).slice(0, 8).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {masterValidation && (
          <div className={`alert alert-${masterValidation.valid ? "success" : "warning"} text-sm`}>
            Master rules v{String(masterValidation.validation_version || "—")}:{" "}
            {masterValidation.valid ? "passed" : `${masterValidation.error_count} error(s)`}
            {Array.isArray(masterValidation.errors) && (masterValidation.errors as string[]).length > 0 && (
              <ul className="mt-2 pl-4">
                {(masterValidation.errors as string[]).slice(0, 8).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </SectionCard>

      <SectionCard title="Latest Summary File">
        {loading ? (
          <span className="spinner" />
        ) : !summary?.available ? (
          <div className="alert alert-warning text-sm">
            No Summary_*.xlsx found. Run step 3 Generate Baseline first.
          </div>
        ) : (
          <>
            <p className="text-sm mb-3">
              <strong>{summary.file}</strong> — {summary.rows?.length ?? 0} rows shown
            </p>
            {summary.rows && summary.rows.length > 0 && (() => {
              const cols = summary.columns || Object.keys(summary.rows[0]);
              return (
                <div className="table-wrap" style={{ maxHeight: 420, overflow: "auto" }}>
                  <table>
                    <thead>
                      <tr>
                        {cols.map(c => (
                          <th key={c}>{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {summary.rows.map((row, i) => (
                        <tr key={i}>
                          {cols.map(c => (
                            <td key={c} style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>
                              {String(row[c] ?? "—")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })()}
          </>
        )}
      </SectionCard>

      <SectionCard title="Base Plan: Previous vs Current">
        <HubSkuComparisonPanel />
      </SectionCard>

      <SectionCard title="Multi-level Comparison">
        <UrlTabs param="view" defaultTab="city-day" keepMounted={false} tabs={comparisonTabs} />
        <p className="text-xs text-muted mt-2">Active view: {activeView}</p>
      </SectionCard>
    </BaselineStepShell>
  );
}

export default function ReviewPage() {
  return (
    <Suspense>
      <ReviewContent />
    </Suspense>
  );
}
