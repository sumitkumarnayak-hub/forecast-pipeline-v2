"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { UrlTabs } from "@/components/ui/UrlTabs";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  RefreshCw,
  Lock,
  DownloadCloud,
  Play,
  BarChart2,
  CheckCircle2,
  XCircle,
  Upload,
  MapPin,
  FileSpreadsheet,
} from "lucide-react";

const BOOTSTRAP_KEY = "final-plan:bootstrap";
const BOOTSTRAP_TTL_MS = 120_000;

type InputCheck = {
  id: string;
  label: string;
  required: boolean;
  exists: boolean;
  sync_action?: string;
  modified?: string;
  size_bytes?: number;
};

type FinalPlanBootstrap = {
  baseline_approved: boolean;
  latest_run: Record<string, unknown> | null;
  runs: Record<string, unknown>[];
  config: Record<string, unknown>;
  inputs: {
    ready: boolean;
    required_ok: boolean;
    inv_logic_ok: boolean;
    inv_logic_count: number;
    inv_logic_files: string[];
    checks: InputCheck[];
  };
  city_mapping: {
    available: boolean;
    rows: Record<string, unknown>[];
    columns: string[];
    row_count?: number;
    message?: string;
  };
  hub_suggestions: {
    rows: Record<string, unknown>[];
    columns: string[];
    message?: string;
  };
  latest_output: Record<string, unknown>;
};

function fmt(dt: string | null | undefined) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function fmtBytes(n: number | undefined) {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function readBootstrapCache(): FinalPlanBootstrap | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(BOOTSTRAP_KEY);
    if (!raw) return null;
    const { ts, data } = JSON.parse(raw) as { ts: number; data: FinalPlanBootstrap };
    if (Date.now() - ts > BOOTSTRAP_TTL_MS) return null;
    return data;
  } catch {
    return null;
  }
}

function writeBootstrapCache(data: FinalPlanBootstrap) {
  try {
    sessionStorage.setItem(BOOTSTRAP_KEY, JSON.stringify({ ts: Date.now(), data }));
  } catch {
    /* ignore quota */
  }
}

function PreviewTable({
  columns,
  rows,
  maxCols = 8,
  maxRows = 30,
}: {
  columns: string[];
  rows: Record<string, unknown>[];
  maxCols?: number;
  maxRows?: number;
}) {
  const cols = columns.slice(0, maxCols);
  if (rows.length === 0) return null;
  return (
    <div className="table-wrap" style={{ maxHeight: 280 }}>
      <table>
        <thead>
          <tr>
            {cols.map(c => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, maxRows).map((row, i) => (
            <tr key={i}>
              {cols.map(c => (
                <td key={c} style={{ fontSize: "0.7rem" }}>
                  {String(row[c] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function FinalPlanPage() {
  const { canWrite } = useAuth();
  const [boot, setBoot] = useState<FinalPlanBootstrap | null>(() => readBootstrapCache());
  const [loading, setLoading] = useState(() => !readBootstrapCache());
  const [syncing, setSyncing] = useState("");
  const [uploading, setUploading] = useState("");
  const [running, setRunning] = useState(false);
  const [runLog, setRunLog] = useState("");
  const [msg, setMsg] = useState({ text: "", type: "" });
  const loadSeq = useRef(0);

  const load = useCallback(async (opts?: { force?: boolean }) => {
    const seq = ++loadSeq.current;
    const cached = !opts?.force ? readBootstrapCache() : null;
    if (cached) {
      setBoot(cached);
      setLoading(false);
    } else {
      setLoading(true);
    }
    try {
      const { data } = await api.get<FinalPlanBootstrap>("/api/final-plan/bootstrap");
      if (seq !== loadSeq.current) return;
      setBoot(data);
      writeBootstrapCache(data);
      setMsg({ text: "", type: "" });
    } catch (e: unknown) {
      if (seq !== loadSeq.current) return;
      if (!cached) {
        const err = e as { response?: { data?: { detail?: string } } };
        setMsg({ text: err?.response?.data?.detail || "Failed to load Final Plan", type: "danger" });
      }
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const invalidateAndReload = async () => {
    try {
      sessionStorage.removeItem(BOOTSTRAP_KEY);
    } catch {
      /* ignore */
    }
    await load({ force: true });
  };

  const doSync = async (action: "adhoc" | "inventory" | "inv-buffer" | "festive" | "city-mapping") => {
    setSyncing(action);
    setMsg({ text: "", type: "" });
    const ep: Record<string, string> = {
      adhoc: "/api/final-plan/sync-adhoc",
      inventory: "/api/final-plan/sync-inventory",
      "inv-buffer": "/api/final-plan/sync-inv-buffer",
      festive: "/api/final-plan/sync-festive",
      "city-mapping": "/api/final-plan/sync-city-mapping",
    };
    try {
      const { data } = await api.post(ep[action]);
      setMsg({ text: data.detail, type: "success" });
      await invalidateAndReload();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Sync failed", type: "danger" });
    }
    setSyncing("");
  };

  const uploadFile = async (kind: string, file: File) => {
    setUploading(kind);
    setMsg({ text: "", type: "" });
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post(`/api/final-plan/upload-input?kind=${kind}`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setMsg({ text: data.detail, type: "success" });
      await invalidateAndReload();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Upload failed", type: "danger" });
    }
    setUploading("");
  };

  const runEngine = async () => {
    setRunning(true);
    setRunLog("");
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/final-plan/run");
      setMsg({
        text: `Run complete — ${data.output_file || data.run_id}`,
        type: "success",
      });
      if (data.stdout_tail) setRunLog(String(data.stdout_tail));
      await invalidateAndReload();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      const detail = err?.response?.data?.detail || "Run failed";
      setMsg({ text: detail, type: "danger" });
      setRunLog(detail);
    }
    setRunning(false);
  };

  const notApproved = !boot?.baseline_approved;
  const inputs = boot?.inputs;
  const inputsReady = inputs?.ready ?? false;
  const hubRows = boot?.hub_suggestions?.rows || [];
  const cityRows = boot?.city_mapping?.rows || [];
  const output = boot?.latest_output;
  const outRows = (output?.preview_rows as Record<string, unknown>[]) || [];
  const runs = boot?.runs || [];

  const inputsTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <FileSpreadsheet size={16} />
          Input Checklist
          {inputs && (
            <span className={`badge badge-${inputsReady ? "green" : "amber"}`} style={{ marginLeft: "auto" }}>
              {inputsReady ? "Ready to run" : "Missing inputs"}
            </span>
          )}
        </div>
        {loading && !inputs ? (
          <span className="spinner" />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {(inputs?.checks || []).map(c => (
              <div
                key={c.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.6rem",
                  padding: "0.5rem 0.65rem",
                  borderRadius: 6,
                  background: "var(--surface-2)",
                  fontSize: "0.82rem",
                }}
              >
                {c.exists ? (
                  <CheckCircle2 size={15} color="var(--green)" />
                ) : (
                  <XCircle size={15} color={c.required ? "var(--red)" : "var(--muted)"} />
                )}
                <span style={{ flex: 1 }}>
                  {c.label}
                  {c.required && !c.exists && <span className="text-muted"> (required)</span>}
                </span>
                {c.exists && c.modified && (
                  <span className="text-xs text-muted">
                    {fmt(c.modified)} · {fmtBytes(c.size_bytes)}
                  </span>
                )}
                {!c.exists && c.sync_action && canWrite && !notApproved && (
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={!!syncing || !!uploading}
                    onClick={() => doSync(c.sync_action as "adhoc" | "inv-buffer" | "festive")}
                  >
                    Sync
                  </button>
                )}
                {canWrite && !notApproved && (
                  <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer", margin: 0 }}>
                    {uploading === c.id ? <span className="spinner" style={{ width: 10, height: 10 }} /> : <Upload size={12} />}
                    <input
                      type="file"
                      accept=".xlsx,.xls"
                      style={{ display: "none" }}
                      disabled={!!uploading || !!syncing}
                      onChange={e => {
                        const f = e.target.files?.[0];
                        if (f) uploadFile(c.id, f);
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
              </div>
            ))}
            {inputs && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.6rem",
                  padding: "0.5rem 0.65rem",
                  borderRadius: 6,
                  background: "var(--surface-2)",
                  fontSize: "0.82rem",
                }}
              >
                {inputs.inv_logic_ok ? (
                  <CheckCircle2 size={15} color="var(--green)" />
                ) : (
                  <XCircle size={15} color="var(--red)" />
                )}
                <span style={{ flex: 1 }}>
                  Inv logic Excel files ({inputs.inv_logic_count} synced)
                </span>
                {canWrite && !notApproved && (
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={!!syncing}
                    onClick={() => doSync("inventory")}
                  >
                    Sync inventory logic
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="grid-2">
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.4rem" }}>Sync from Sheets</div>
          <div className="text-xs text-muted" style={{ marginBottom: "1rem" }}>
            Pull adhoc adjustments, inventory logic, inv buffer, city mapping, and festive template.
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {(
              [
                ["adhoc", "Sync Adhoc"],
                ["inventory", "Sync Inventory Logic"],
                ["inv-buffer", "Sync Inv Buffer"],
                ["city-mapping", "Sync City Mapping"],
                ["festive", "Ensure Festive.xlsx"],
              ] as const
            ).map(([action, label]) => (
              <button
                key={action}
                className="btn btn-secondary w-full"
                onClick={() => doSync(action)}
                disabled={!!syncing || notApproved || !canWrite}
              >
                {syncing === action ? (
                  <span className="spinner" style={{ width: 12, height: 12 }} />
                ) : (
                  <DownloadCloud size={14} />
                )}
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <MapPin size={15} /> City Mapping Preview
          </div>
          {cityRows.length === 0 ? (
            <p className="text-xs text-muted">
              {boot?.city_mapping?.message || "Load city mapping from Demand Planning Masters."}
            </p>
          ) : (
            <>
              <p className="text-xs text-muted mb-2">
                {boot?.city_mapping?.row_count?.toLocaleString()} rows from sheet
              </p>
              <PreviewTable columns={boot?.city_mapping?.columns || []} rows={cityRows} />
            </>
          )}
        </div>

        <div className="card" style={{ gridColumn: "1 / -1" }}>
          <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Hub Suggestions Preview</div>
          {hubRows.length === 0 ? (
            <p className="text-xs text-muted">
              {boot?.hub_suggestions?.message || "No hub suggestion cache — run baseline first."}
            </p>
          ) : (
            <PreviewTable columns={boot?.hub_suggestions?.columns || []} rows={hubRows} />
          )}
        </div>
      </div>
    </div>
  );

  const runTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.75rem" }}>Pre-run Check</div>
        <ul className="text-sm" style={{ margin: 0, paddingLeft: "1.2rem" }}>
          <li style={{ color: boot?.baseline_approved ? "var(--green)" : "var(--red)" }}>
            Baseline approved {boot?.baseline_approved ? "✓" : "✗"}
          </li>
          <li style={{ color: inputs?.required_ok ? "var(--green)" : "var(--red)" }}>
            Required FF input files {inputs?.required_ok ? "✓" : "✗"}
          </li>
          <li style={{ color: inputs?.inv_logic_ok ? "var(--green)" : "var(--red)" }}>
            Inventory logic files ({inputs?.inv_logic_count ?? 0}) {inputs?.inv_logic_ok ? "✓" : "✗"}
          </li>
        </ul>
        <p className="text-xs text-muted mt-3">
          Runs <code>ff_hub_automation_cluster_change.py</code> — may take several minutes.
        </p>
        <button
          className="btn btn-primary mt-3"
          disabled={notApproved || !canWrite || running || !inputsReady}
          onClick={runEngine}
        >
          {running ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Play size={14} />}
          {running ? "Running…" : "Run Final Plan"}
        </button>
        {!inputsReady && !notApproved && (
          <p className="text-xs text-muted mt-2">Complete the input checklist on the Inputs tab before running.</p>
        )}
      </div>

      {(running || runLog) && (
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Run Log</div>
          {running && !runLog && <span className="spinner" />}
          {runLog && (
            <pre
              style={{
                fontSize: "0.68rem",
                maxHeight: 320,
                overflow: "auto",
                background: "var(--surface-2)",
                padding: "0.75rem",
                borderRadius: 6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {runLog}
            </pre>
          )}
        </div>
      )}

      {boot?.latest_run && (
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Latest Run</div>
          <p className="text-sm">
            <strong>{String(boot.latest_run.run_name)}</strong> — {String(boot.latest_run.status)} ·{" "}
            {fmt(boot.latest_run.run_date as string)}
          </p>
        </div>
      )}
    </div>
  );

  const outputTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <BarChart2 size={16} /> Latest Hub_Dist Output
        </div>
        {!output?.available ? (
          <p className="text-xs text-muted">{String(output?.message || "No output file yet.")}</p>
        ) : (
          <>
            <p className="text-sm mb-2">
              <strong>{String(output.file)}</strong> — {Number(output.rows).toLocaleString()} rows
              {output.validation ? (
                <span
                  className={`badge badge-${(output.validation as { valid?: boolean }).valid ? "green" : "red"} ml-2`}
                >
                  {(output.validation as { valid?: boolean }).valid ? "Valid" : "Invalid"}
                </span>
              ) : null}
            </p>
            <PreviewTable
              columns={(output.columns as string[]) || []}
              rows={outRows}
              maxCols={10}
              maxRows={50}
            />
          </>
        )}
      </div>

      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.75rem" }}>Run History</div>
        {loading && runs.length === 0 ? (
          <span className="spinner" />
        ) : runs.length === 0 ? (
          <p className="text-xs text-muted">No runs recorded.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Status</th>
                  <th>Date</th>
                  <th>Output</th>
                  <th>Validation</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(r => (
                  <tr key={String(r.run_id)}>
                    <td style={{ fontFamily: "monospace", fontSize: "0.68rem" }}>{String(r.run_id).slice(-10)}</td>
                    <td>{String(r.status)}</td>
                    <td style={{ fontSize: "0.72rem" }}>{fmt(r.run_date as string | null)}</td>
                    <td style={{ fontSize: "0.7rem", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {String(r.output_file || "—")}
                    </td>
                    <td>{String(r.validation_status || "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <AppShell
      title="Final Plan"
      subtitle="Sync inputs, generate and approve the final distribution plan"
      actions={
        <button className="btn btn-secondary btn-sm" onClick={() => load({ force: true })} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {notApproved && boot && (
        <div className="alert alert-warning mb-4">
          <Lock size={15} /> Baseline not approved — Final Plan is locked.
        </div>
      )}
      {msg.text && <div className={`alert alert-${msg.type} mb-4`}>{msg.text}</div>}
      <UrlTabs
        defaultTab="inputs"
        tabs={[
          { id: "inputs", label: "Inputs", content: inputsTab },
          { id: "run", label: "Run", content: runTab },
          { id: "output", label: "Output", content: outputTab },
        ]}
      />
    </AppShell>
  );
}
