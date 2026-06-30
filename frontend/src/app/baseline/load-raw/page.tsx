"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import BaselineStepShell from "@/components/baseline/BaselineStepShell";
import SectionCard from "@/components/baseline/SectionCard";
import api from "@/lib/api";
import { useCachedQuery } from "@/hooks/useCachedQuery";
import { cacheInvalidate } from "@/lib/queryCache";
import { useAuth } from "@/hooks/useAuth";
import { ChevronDown, ChevronUp, Download, FolderOpen, RefreshCw } from "lucide-react";

interface RepoRow {
  week: number;
  week_label: string;
  rows: number | null;
  total_sales: number | null;
  total_net_sales: number | null;
  format: string;
}

interface RawStatus {
  repository: { weeks: number[]; summary_rows: RepoRow[]; empty: boolean };
  active_dataset: {
    exists: boolean;
    rows: number | null;
    weeks: number[];
    source: string;
    preview_rows: Record<string, unknown>[];
  };
  dates: { start_date: string; end_date: string };
}

const CACHE_KEY = "baseline:raw-status";

function LoadRawContent() {
  const { readOnly } = useAuth();
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedWeeks, setSelectedWeeks] = useState<number[]>([]);
  const [saveCsv, setSaveCsv] = useState(false);
  const [useCache, setUseCache] = useState(true);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkPlan, setBulkPlan] = useState<
    { iso_week: number; start_date: string; end_date: string; already_saved: boolean }[]
  >([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [statsOpen, setStatsOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailRows, setDetailRows] = useState<RepoRow[] | null>(null);

  const fetchStatus = useCallback(async () => {
    const { data } = await api.get<RawStatus>("/api/baseline/raw-data/status");
    return data;
  }, []);

  const { data: status, loading, refreshing, refresh } = useCachedQuery<RawStatus>(
    CACHE_KEY,
    fetchStatus,
    { ttlMs: 180_000 },
  );

  // Hydrate date inputs immediately when status arrives (or from cache)
  useEffect(() => {
    if (!status?.dates) return;
    setStartDate(prev => prev || status.dates.start_date || "");
    setEndDate(prev => prev || status.dates.end_date || "");
    const weeks: number[] = status.repository?.weeks || [];
    setSelectedWeeks(prev => (prev.length ? prev.filter(w => weeks.includes(w)) : weeks));
  }, [status]);

  const loadStatus = useCallback(
    (force = true) => {
      if (force) cacheInvalidate(CACHE_KEY);
      return refresh(force);
    },
    [refresh],
  );

  const loadDetails = useCallback(async () => {
    if (detailRows) return;
    setDetailsLoading(true);
    try {
      const { data } = await api.get<{ repository: { summary_rows: RepoRow[] } }>(
        "/api/baseline/raw-data/status/details",
      );
      setDetailRows(data.repository?.summary_rows || []);
    } catch {
      /* keep lite rows */
    } finally {
      setDetailsLoading(false);
    }
  }, [detailRows]);

  useEffect(() => {
    if (statsOpen && !detailRows && !detailsLoading) {
      loadDetails();
    }
  }, [statsOpen, detailRows, detailsLoading, loadDetails]);

  const loadBulkPlan = useCallback(async () => {
    setBulkLoading(true);
    try {
      const { data } = await api.get("/api/baseline/raw-data/bulk-plan");
      setBulkPlan(data);
    } catch {
      setBulkPlan([]);
    } finally {
      setBulkLoading(false);
    }
  }, []);

  useEffect(() => {
    if (bulkOpen && bulkPlan.length === 0) loadBulkPlan();
  }, [bulkOpen, bulkPlan.length, loadBulkPlan]);

  const runBulkPull = async () => {
    setBusy("bulk");
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/baseline/raw-data/bulk-pull", {
        also_save_csv: saveCsv,
      });
      setMsg({ text: data.detail, type: "success" });
      cacheInvalidate(CACHE_KEY);
      setDetailRows(null);
      await loadStatus(true);
      await loadBulkPlan();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Bulk pull failed", type: "danger" });
    } finally {
      setBusy("");
    }
  };

  const saveDates = async () => {
    if (!startDate || !endDate) return;
    setBusy("dates");
    try {
      await api.post("/api/baseline/raw-data/dates", { start_date: startDate, end_date: endDate });
    } catch {
      /* non-fatal */
    } finally {
      setBusy("");
    }
  };

  const fetchRaw = async () => {
    setBusy("fetch");
    setMsg({ text: "", type: "" });
    await saveDates();
    try {
      const { data } = await api.post("/api/baseline/raw-data/fetch", {
        start_date: startDate,
        end_date: endDate,
        also_save_csv: saveCsv,
        use_cached_week: useCache,
      });
      setMsg({ text: data.detail, type: "success" });
      cacheInvalidate(CACHE_KEY);
      setDetailRows(null);
      await loadStatus(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Fetch failed", type: "danger" });
    } finally {
      setBusy("");
    }
  };

  const loadWeeks = async () => {
    if (!selectedWeeks.length) {
      setMsg({ text: "Select at least one week", type: "warning" });
      return;
    }
    setBusy("load");
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/baseline/raw-data/load-weeks", { weeks: selectedWeeks });
      setMsg({ text: data.detail, type: "success" });
      cacheInvalidate(CACHE_KEY);
      await loadStatus(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Load failed", type: "danger" });
    } finally {
      setBusy("");
    }
  };

  const weeks = status?.repository?.weeks || [];
  const active = status?.active_dataset;
  const repoRows = detailRows ?? status?.repository?.summary_rows ?? [];
  const datesReady = Boolean(startDate && endDate);

  return (
    <BaselineStepShell
      stepId="load-raw"
      actions={
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => loadStatus(true)}
          disabled={loading || refreshing}
        >
          <RefreshCw size={13} className={loading || refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {msg.text && <div className={`alert alert-${msg.type} mb-4`}>{msg.text}</div>}

      <SectionCard title="Select Date Range" description="Max 7 days — synced to Pipeline Params sheet.">
        <div className="grid-2" style={{ maxWidth: 480 }}>
          <div className="form-group">
            <label className="form-label">Start Date</label>
            <input
              type="date"
              className="form-input"
              value={startDate}
              onChange={e => setStartDate(e.target.value)}
              disabled={readOnly}
            />
          </div>
          <div className="form-group">
            <label className="form-label">End Date</label>
            <input
              type="date"
              className="form-input"
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
              disabled={readOnly}
            />
          </div>
        </div>
        {!datesReady && loading && (
          <p className="text-xs text-muted mt-2">Loading saved dates…</p>
        )}
        <label style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }} className="text-sm">
          <input type="checkbox" checked={saveCsv} onChange={e => setSaveCsv(e.target.checked)} disabled={readOnly} />
          Also save CSV copy
        </label>
        <label style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }} className="text-sm">
          <input type="checkbox" checked={useCache} onChange={e => setUseCache(e.target.checked)} disabled={readOnly} />
          Use cached week parquet if available
        </label>
        <button
          type="button"
          className="btn btn-primary mt-4"
          disabled={readOnly || busy === "fetch" || !datesReady}
          onClick={fetchRaw}
        >
          {busy === "fetch" ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Download size={14} />}
          Fetch Raw Data
        </button>
      </SectionCard>

      <SectionCard title="Repository Status" description="Week parquet/xlsx files on disk.">
        {loading && weeks.length === 0 ? (
          <span className="spinner" />
        ) : weeks.length === 0 ? (
          <div className="alert alert-info text-sm">Repository is empty. Fetch a week to get started.</div>
        ) : (
          <>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-600 mb-3"
              onClick={() => setStatsOpen(v => !v)}
            >
              {statsOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              {statsOpen ? "Hide row statistics" : "Show row statistics (loads on demand)"}
            </button>
            {(statsOpen || detailRows) && (
              <div className="table-wrap">
                {detailsLoading && (
                  <p className="text-xs text-muted mb-2">Loading row counts…</p>
                )}
                <table>
                  <thead>
                    <tr>
                      <th>Week</th>
                      <th>Rows</th>
                      <th>Total Sales</th>
                      <th>Sales (w/o Liq)</th>
                      <th>Format</th>
                    </tr>
                  </thead>
                  <tbody>
                    {repoRows.map(r => (
                      <tr key={r.week}>
                        <td>{r.week_label}</td>
                        <td>{r.rows?.toLocaleString() ?? "—"}</td>
                        <td>{r.total_sales != null ? r.total_sales.toLocaleString() : "—"}</td>
                        <td>{r.total_net_sales != null ? r.total_net_sales.toLocaleString() : "—"}</td>
                        <td>{r.format}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!statsOpen && !detailRows && (
              <p className="text-sm text-muted">{weeks.length} week(s) on disk: {weeks.join(", ")}</p>
            )}
          </>
        )}
      </SectionCard>

      <SectionCard title="One-Time Bulk Pull — Past 10 Weeks">
        <button
          type="button"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-600"
          onClick={() => setBulkOpen(v => !v)}
        >
          {bulkOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          Expand bulk pull
        </button>
        {bulkOpen && (
          <div className="mt-3">
            {bulkLoading ? (
              <span className="spinner" />
            ) : (
              <>
                <p className="text-xs text-muted mb-3">
                  Pulls the past 10 ISO weeks from RDS into repository parquets (Streamlit parity).
                </p>
                <div className="table-wrap mb-4">
                  <table>
                    <thead>
                      <tr>
                        <th>ISO Week</th>
                        <th>Start</th>
                        <th>End</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bulkPlan.map(w => (
                        <tr key={w.iso_week}>
                          <td>Wk {w.iso_week}</td>
                          <td>{w.start_date}</td>
                          <td>{w.end_date}</td>
                          <td>{w.already_saved ? "On disk" : "Pending"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={readOnly || busy === "bulk"}
                  onClick={runBulkPull}
                >
                  {busy === "bulk" ? (
                    <span className="spinner" style={{ width: 14, height: 14 }} />
                  ) : (
                    <Download size={14} />
                  )}
                  Pull past 10 weeks
                </button>
              </>
            )}
          </div>
        )}
      </SectionCard>

      <SectionCard title="Load Repository into Session">
        <div className="form-group">
          <label className="form-label">Weeks to load (Ctrl+click for multiple)</label>
          <select
            className="form-input"
            multiple
            disabled={readOnly || !weeks.length}
            style={{ minHeight: 120 }}
            value={selectedWeeks.map(String)}
            onChange={e => {
              const opts = Array.from(e.target.selectedOptions).map(o => Number(o.value));
              setSelectedWeeks(opts);
            }}
          >
            {weeks.map(w => (
              <option key={w} value={w}>
                Week {w}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="btn btn-primary mt-3"
          disabled={readOnly || busy === "load" || !selectedWeeks.length}
          onClick={loadWeeks}
        >
          {busy === "load" ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <FolderOpen size={14} />}
          Load selected weeks
        </button>
      </SectionCard>

      {active?.exists && (
        <SectionCard title="Active dataset in session">
          <p className="text-sm">
            <strong>{active.rows?.toLocaleString() ?? "—"}</strong> rows from weeks{" "}
            {(active.weeks || []).join(", ") || "—"}
          </p>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-600 mt-2"
            onClick={() => setPreviewOpen(v => !v)}
          >
            {previewOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            Preview
          </button>
          {previewOpen && (
            <div className="table-wrap mt-3" style={{ maxHeight: 280 }}>
              <table>
                <thead>
                  <tr>
                    {active.preview_rows?.[0]
                      ? Object.keys(active.preview_rows[0]).map(k => <th key={k}>{k}</th>)
                      : null}
                  </tr>
                </thead>
                <tbody>
                  {(active.preview_rows || []).slice(0, 50).map((row, idx) => (
                    <tr key={idx}>
                      {Object.keys(row).map(k => (
                        <td key={k} style={{ fontSize: "0.72rem" }}>
                          {String(row[k] ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      )}
    </BaselineStepShell>
  );
}

export default function LoadRawPage() {
  return (
    <Suspense>
      <LoadRawContent />
    </Suspense>
  );
}
