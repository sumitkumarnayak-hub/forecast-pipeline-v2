"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { UrlTabs } from "@/components/ui/UrlTabs";
import { ValidationResult, fmtFileTime } from "@/components/validation/ValidationResult";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { Upload, Play, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { useInstantBootstrap } from "@/hooks/useInstantBootstrap";
import TableSkeleton from "@/components/ui/TableSkeleton";

const BOOTSTRAP_KEY = "validation:bootstrap";

type Bootstrap = {
  logics?: {
    validation_version?: string;
    input_types?: { id: string; label: string }[];
    master_options?: { id: string; label: string }[];
    rules?: string[];
    baseline_schema?: string[];
  };
  outputs?: {
    baseline?: { available: boolean; file?: string; modified?: number };
    final_plan?: { available: boolean; file?: string; modified?: number };
  };
  history_count?: number;
};

function ValidationContent() {
  const { canWrite } = useAuth();
  const { data: boot, loading, reload } = useInstantBootstrap<Bootstrap>(
    BOOTSTRAP_KEY,
    "/api/validation/bootstrap",
  );
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [busy, setBusy] = useState("");

  const [inputType, setInputType] = useState("raw_data");
  const inputRef = useRef<HTMLInputElement>(null);
  const outputRef = useRef<HTMLInputElement>(null);
  const [inputResult, setInputResult] = useState<Record<string, unknown> | null>(null);
  const [masterId, setMasterId] = useState("product_hub_master");
  const [masterResult, setMasterResult] = useState<Record<string, unknown> | null>(null);
  const [outputResult, setOutputResult] = useState<Record<string, unknown> | null>(null);
  const [history, setHistory] = useState<Record<string, unknown>[]>([]);

  const loadHistory = useCallback(async () => {
    try {
      const { data } = await api.get<{ rows: Record<string, unknown>[] }>("/api/validation/history");
      setHistory(data.rows || []);
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const afterRun = async (text: string, type: string) => {
    setMsg({ text, type });
    await loadHistory();
    await reload(true);
  };

  const runInputValidation = async (file: File) => {
    setBusy("input");
    setInputResult(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post(`/api/validation/validate-input?data_type=${inputType}`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setInputResult(data);
      await afterRun(
        `${file.name} — ${data.valid ? "passed" : "failed"}`,
        data.valid ? "success" : "danger",
      );
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Validation failed", type: "danger" });
    }
    setBusy("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const runMasterValidation = async () => {
    setBusy("master");
    setMasterResult(null);
    try {
      const { data } = await api.post(`/api/validation/validate-master?master_id=${masterId}`);
      setMasterResult(data);
      await afterRun(
        data.valid ? "Master validation passed" : `${data.error_count} errors`,
        data.valid ? "success" : "danger",
      );
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Failed", type: "danger" });
    }
    setBusy("");
  };

  const validateLatest = async (kind: "baseline" | "final-plan") => {
    setBusy(kind);
    setOutputResult(null);
    try {
      const { data } = await api.get(`/api/validation/validate-latest/${kind}`);
      setOutputResult(data);
      await afterRun(
        `Validated ${data.file}`,
        data.validation?.valid ? "success" : "danger",
      );
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Not found", type: "warning" });
    }
    setBusy("");
  };

  const uploadBaseline = async (file: File) => {
    setBusy("upload");
    setOutputResult(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post("/api/validation/validate-baseline-output", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setOutputResult({ file: data.filename, validation: data.validation, rows: data.rows });
      await afterRun(
        `${file.name} — ${data.validation?.valid ? "passed" : "failed"}`,
        data.validation?.valid ? "success" : "danger",
      );
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Upload failed", type: "danger" });
    }
    setBusy("");
    if (outputRef.current) outputRef.current.value = "";
  };

  const clearHistory = async () => {
    try {
      await api.delete("/api/validation/history");
      setHistory([]);
      setMsg({ text: "History cleared", type: "success" });
      await reload(true);
    } catch {
      setMsg({ text: "Could not clear history", type: "danger" });
    }
  };

  const logics = boot?.logics;
  const outputs = boot?.outputs;

  const inputTab = (
    <div className="grid-2">
      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.75rem" }}>Upload input file</div>
        <p className="text-xs text-muted mb-3">
          Validate raw sales, hub changes, outlier days, or percentile data before processing.
        </p>
        <div className="form-group">
          <label className="form-label">Data type</label>
          <select className="form-input" value={inputType} onChange={e => setInputType(e.target.value)}>
            {(logics?.input_types || []).map(t => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>
        </div>
        {canWrite ? (
          <label className="btn btn-primary btn-sm" style={{ cursor: "pointer" }}>
            {busy === "input" ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <Upload size={13} />}
            Upload CSV / Excel
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              style={{ display: "none" }}
              disabled={!!busy}
              onChange={e => {
                const f = e.target.files?.[0];
                if (f) runInputValidation(f);
              }}
            />
          </label>
        ) : (
          <div className="alert alert-warning text-sm">Read-only — uploads disabled</div>
        )}
      </div>
      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.75rem" }}>Result</div>
        <ValidationResult
          validation={inputResult as { valid?: boolean; errors?: string[]; warnings?: string[] }}
          filename={inputResult?.filename as string}
          rows={inputResult?.rows as number}
        />
      </div>
    </div>
  );

  const masterTab = (
    <div className="grid-2">
      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.75rem" }}>Master sheet validation</div>
        <div className="form-group">
          <label className="form-label">Select master</label>
          <select className="form-input" value={masterId} onChange={e => setMasterId(e.target.value)}>
            {(logics?.master_options || []).map(m => (
              <option key={m.id} value={m.id}>{m.label}</option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={!canWrite || busy === "master"}
          onClick={runMasterValidation}
        >
          {busy === "master" ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <Play size={13} />}
          Run validation
        </button>
        <p className="text-xs text-muted mt-2">P-H Master runs full Polars rules against live Google Sheets.</p>
      </div>
      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.75rem" }}>Result</div>
        <ValidationResult
          validation={
            masterResult
              ? {
                  valid: masterResult.valid as boolean,
                  errors: masterResult.errors as string[],
                  warnings: masterResult.warnings as string[],
                  stats: masterResult.stats as Record<string, unknown>,
                }
              : null
          }
        />
      </div>
    </div>
  );

  const outputTab = (
    <div className="grid-2">
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>
            <ShieldCheck size={15} /> Baseline output
          </div>
          {outputs?.baseline?.available ? (
            <p className="text-xs text-muted mb-2">
              Latest: <strong>{outputs.baseline.file}</strong>
              {outputs.baseline.modified ? ` · ${fmtFileTime(outputs.baseline.modified)}` : ""}
            </p>
          ) : (
            <p className="text-xs text-muted mb-2">No Summary_*.xlsx on disk.</p>
          )}
          <button
            type="button"
            className="btn btn-secondary btn-sm mb-2"
            disabled={!!busy || !outputs?.baseline?.available}
            onClick={() => validateLatest("baseline")}
          >
            Validate latest Summary
          </button>
          {canWrite && (
            <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer", marginLeft: 8 }}>
              <Upload size={12} /> Upload Summary
              <input
                ref={outputRef}
                type="file"
                accept=".xlsx"
                style={{ display: "none" }}
                disabled={!!busy}
                onChange={e => {
                  const f = e.target.files?.[0];
                  if (f) uploadBaseline(f);
                }}
              />
            </label>
          )}
        </div>
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Final plan output</div>
          {outputs?.final_plan?.available ? (
            <p className="text-xs text-muted mb-2">
              Latest: <strong>{outputs.final_plan.file}</strong>
              {outputs.final_plan.modified ? ` · ${fmtFileTime(outputs.final_plan.modified)}` : ""}
            </p>
          ) : (
            <p className="text-xs text-muted mb-2">No Hub_Dist_Wk*.xlsx on disk.</p>
          )}
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={!!busy || !outputs?.final_plan?.available}
            onClick={() => validateLatest("final-plan")}
          >
            Validate latest Hub_Dist
          </button>
        </div>
      </div>
      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.75rem" }}>Result</div>
        <ValidationResult
          validation={outputResult?.validation as { valid?: boolean; errors?: string[]; warnings?: string[] }}
          filename={(outputResult?.file as string) || undefined}
          rows={(outputResult?.validation as { stats?: { rows?: number } })?.stats?.rows}
        />
      </div>
    </div>
  );

  const historyTab = (
    <div>
      <div className="flex justify-between items-center mb-3">
        <p className="text-sm text-muted">
          {history.length} run{history.length !== 1 ? "s" : ""} this session
          {logics?.validation_version && ` · rules v${logics.validation_version}`}
        </p>
        <div className="flex gap-2">
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadHistory}>
            <RefreshCw size={12} /> Refresh
          </button>
          {canWrite && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={clearHistory}>
              <Trash2 size={12} /> Clear
            </button>
          )}
        </div>
      </div>
      {history.length === 0 ? (
        <div className="card text-sm text-muted">No validation runs yet — use another tab to run a check.</div>
      ) : (
        <div className="card table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Status</th>
                <th>Run / File</th>
                <th>Errors</th>
              </tr>
            </thead>
            <tbody>
              {history.map((row, i) => (
                <tr key={i}>
                  <td style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>{String(row.validation_date)}</td>
                  <td style={{ fontSize: "0.75rem" }}>{String(row.validation_type)}</td>
                  <td>
                    <span className={`badge badge-${row.passed ? "green" : "red"}`}>{String(row.passed_label)}</span>
                  </td>
                  <td style={{ fontSize: "0.72rem" }}>{String(row.filename || row.run_id || "—")}</td>
                  <td style={{ fontSize: "0.68rem", maxWidth: 280 }}>{String(row.errors_display || "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {logics?.rules && (
        <details className="card mt-4 text-sm">
          <summary style={{ fontWeight: 700, cursor: "pointer" }}>Validation rules reference</summary>
          <ul className="mt-2 text-xs">
            {logics.rules.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          <p className="text-xs text-muted mt-2">Baseline schema: {logics.baseline_schema?.join(", ")}</p>
        </details>
      )}
    </div>
  );

  return (
    <AppShell
      title="Validation"
      subtitle="Input, master, and output data quality checks"
      actions={
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => reload(true)} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {msg.text && <div className={`alert alert-${msg.type} mb-4`}>{msg.text}</div>}
      {loading && !boot ? (
        <TableSkeleton rows={5} cols={4} />
      ) : (
        <UrlTabs
          defaultTab="input"
          keepMounted={false}
          tabs={[
            { id: "input", label: "Input Validation", content: inputTab },
            { id: "master", label: "Master Validation", content: masterTab },
            { id: "output", label: "Output Validation", content: outputTab },
            { id: "history", label: "Validation History", content: historyTab },
          ]}
        />
      )}
    </AppShell>
  );
}

export default function ValidationPage() {
  return (
    <Suspense>
      <ValidationContent />
    </Suspense>
  );
}
