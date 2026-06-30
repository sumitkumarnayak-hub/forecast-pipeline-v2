"use client";

import { CheckCircle, XCircle, AlertTriangle } from "lucide-react";

type ValidationPayload = {
  valid?: boolean;
  errors?: string[];
  warnings?: string[];
  stats?: Record<string, unknown>;
};

export function ValidationResult({
  validation,
  filename,
  rows,
}: {
  validation?: ValidationPayload | null;
  filename?: string;
  rows?: number;
}) {
  if (!validation) {
    return <p className="text-sm text-muted text-center py-6">No result yet.</p>;
  }

  const passed = validation.valid !== false;
  const errors = validation.errors || [];
  const warnings = validation.warnings || [];

  return (
    <div>
      {filename && (
        <p className="text-sm mb-2">
          <strong>{filename}</strong>
          {rows != null && ` — ${rows.toLocaleString()} rows`}
        </p>
      )}
      <div className="flex gap-2 mb-3">
        <span className={`badge badge-${passed ? "green" : "red"}`}>
          {passed ? <CheckCircle size={11} /> : <XCircle size={11} />}
          {passed ? "Passed" : "Failed"}
        </span>
      </div>
      {validation.stats && Object.keys(validation.stats).length > 0 && (
        <div className="stat-grid mb-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))" }}>
          {Object.entries(validation.stats).map(([k, v]) => (
            <div key={k} className="stat-card" style={{ padding: "0.5rem 0.65rem" }}>
              <div className="stat-label" style={{ fontSize: "0.65rem" }}>{k}</div>
              <div className="stat-value" style={{ fontSize: "1rem" }}>{String(v)}</div>
            </div>
          ))}
        </div>
      )}
      {errors.map((e, i) => (
        <div key={`e-${i}`} className="text-xs mb-1" style={{ color: "var(--red)" }}>
          • {e}
        </div>
      ))}
      {warnings.map((w, i) => (
        <div key={`w-${i}`} className="text-xs mb-1" style={{ color: "var(--amber, #f59e0b)" }}>
          <AlertTriangle size={11} style={{ display: "inline", marginRight: 4 }} />
          {w}
        </div>
      ))}
    </div>
  );
}

export function fmtFileTime(ts?: number) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}
