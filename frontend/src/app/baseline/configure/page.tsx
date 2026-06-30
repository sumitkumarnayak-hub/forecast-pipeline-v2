"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import BaselineStepShell from "@/components/baseline/BaselineStepShell";
import SectionCard from "@/components/baseline/SectionCard";
import api from "@/lib/api";
import { useCachedQuery } from "@/hooks/useCachedQuery";
import { cacheInvalidate } from "@/lib/queryCache";
import { useAuth } from "@/hooks/useAuth";
import { ExternalLink, RefreshCw } from "lucide-react";

function ConfigureContent() {
  const { readOnly } = useAuth();
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [dpStatus, setDpStatus] = useState<{ worksheet: string; status: string; last_updated: string | null }[]>([]);
  const [sheetUrl, setSheetUrl] = useState("");
  const [activeReady, setActiveReady] = useState(false);
  const [sidecars, setSidecars] = useState<Record<string, unknown>[]>([]);
  const [fetchingPrev, setFetchingPrev] = useState(false);
  const [prevPreview, setPrevPreview] = useState<Record<string, unknown> | null>(null);
  const [targetWeek, setTargetWeek] = useState(28);
  const [targetYear, setTargetYear] = useState(2026);

  const [flags, setFlags] = useState({
    use_clustering: true,
    remove_outliers: true,
    apply_hub_changes: true,
    use_availability: true,
    use_stf: true,
    use_percentile: true,
    weeks_back: 4,
    avail_threshold: 0.2,
  });

  const fetchParams = useCallback(async () => {
    const { data } = await api.get("/api/baseline/params");
    return data;
  }, []);

  const { data, loading, refreshing, refresh } = useCachedQuery(
    "baseline:params",
    fetchParams,
    { ttlMs: 180_000 },
  );

  useEffect(() => {
    if (!data) return;
    const p = data.params || {};
    setFlags({
      use_clustering: Boolean(p.use_clustering ?? true),
      remove_outliers: Boolean(p.remove_outliers ?? true),
      apply_hub_changes: Boolean(p.apply_hub_changes ?? true),
      use_availability: Boolean(p.use_availability ?? true),
      use_stf: Boolean(p.use_stf ?? true),
      use_percentile: Boolean(p.use_percentile ?? true),
      weeks_back: Number(p.weeks_back ?? 4),
      avail_threshold: Number(p.avail_threshold ?? 0.2),
    });
    setDpStatus(data.dp_worksheets_status || []);
    setActiveReady(Boolean(data.active_dataset_ready));
    setSheetUrl(data.dp_logics_sheet_url || "");
    setTargetWeek(Number(p.target_week) || 28);
    setTargetYear(Number(p.target_year) || 2026);
  }, [data]);

  const load = useCallback(
    (force = true) => {
      if (force) cacheInvalidate("baseline:params");
      return refresh(force);
    },
    [refresh],
  );

  const saveParams = async () => {
    setSaving(true);
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/baseline/params", flags);
      setMsg({ text: "Parameters saved to Google Sheet", type: "success" });
      cacheInvalidate("baseline:params");
      await load(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Save failed", type: "danger" });
    } finally {
      setSaving(false);
    }
  };

  const syncDp = async () => {
    setSyncing(true);
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.post("/api/baseline/sync-dp-logics");
      setMsg({ text: data.detail || "Sync complete", type: "success" });
      if (data.sidecars) setSidecars(data.sidecars);
      await load(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Sync failed", type: "danger" });
    } finally {
      setSyncing(false);
    }
  };

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
        text: `Previous baseline loaded — ${Number(data.rows || 0).toLocaleString()} rows`,
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

  return (
    <BaselineStepShell
      stepId="configure"
      actions={
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => load(true)} disabled={loading || refreshing}>
          <RefreshCw size={13} className={loading || refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {msg.text && <div className={`alert alert-${msg.type} mb-4`}>{msg.text}</div>}

      {!activeReady && (
        <div className="alert alert-warning text-sm mb-4">
          Load raw data first — open <strong>1. Load Raw Data</strong> and click Load Selected Weeks.
        </div>
      )}

      <SectionCard title="Edit Parameters" description="Saved to Pipeline Params Google Sheet.">
        {loading && !data ? (
          <span className="spinner" />
        ) : (
          <>
            <div className="grid-2 mb-4">
              {(
                [
                  ["use_clustering", "Use Clustering"],
                  ["remove_outliers", "Remove Outliers"],
                  ["apply_hub_changes", "Apply Hub & KML Changes"],
                  ["use_availability", "Use Availability"],
                  ["use_stf", "Use Sell-Through Factor"],
                  ["use_percentile", "Use Percentile"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} style={{ display: "flex", gap: "0.5rem" }} className="text-sm">
                  <input
                    type="checkbox"
                    checked={flags[key]}
                    onChange={e => setFlags(f => ({ ...f, [key]: e.target.checked }))}
                    disabled={readOnly}
                  />
                  {label}
                </label>
              ))}
            </div>
            <div className="grid-2" style={{ maxWidth: 400 }}>
              <div className="form-group">
                <label className="form-label">Weeks Back</label>
                <input
                  type="number"
                  className="form-input"
                  value={flags.weeks_back}
                  onChange={e => setFlags(f => ({ ...f, weeks_back: Number(e.target.value) }))}
                  disabled={readOnly}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Availability Threshold</label>
                <input
                  type="number"
                  step="0.01"
                  className="form-input"
                  value={flags.avail_threshold}
                  onChange={e => setFlags(f => ({ ...f, avail_threshold: Number(e.target.value) }))}
                  disabled={readOnly}
                />
              </div>
            </div>
            <button type="button" className="btn btn-primary mt-3" onClick={saveParams} disabled={readOnly || saving}>
              {saving ? "Saving…" : "Save Parameters"}
            </button>
          </>
        )}
      </SectionCard>

      <SectionCard title="Parameters from Google Sheet">
        {Object.keys(data?.params || {}).length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data?.params || {}).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k}</td>
                    <td style={{ fontSize: "0.8rem" }}>{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Configuration Masters">
        {sheetUrl && (
          <a href={sheetUrl} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm mb-4">
            <ExternalLink size={13} /> Open DP Logics Sheet
          </a>
        )}
        <div className="table-wrap mb-4">
          <table>
            <thead>
              <tr>
                <th>Worksheet</th>
                <th>Status</th>
                <th>Last Updated</th>
              </tr>
            </thead>
            <tbody>
              {dpStatus.map(row => (
                <tr key={row.worksheet}>
                  <td>{row.worksheet}</td>
                  <td>{row.status === "saved" ? "Saved" : "Not synced"}</td>
                  <td>{row.last_updated || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button type="button" className="btn btn-primary" onClick={syncDp} disabled={readOnly || syncing}>
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          Sync All &amp; Save as Excel
        </button>
        {sidecars.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-semibold mb-2">Engine sidecars refreshed</p>
            <ul className="text-xs text-muted">
              {sidecars.map((s, i) => (
                <li key={i}>{JSON.stringify(s)}</li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-xs text-muted mt-3">
          Hub changes are edited under <a href="/master-data?tab=demand">Master Data → Hub Changes</a>.
        </p>
      </SectionCard>

      <SectionCard title="Previous Baseline Cache">
        <p className="text-xs text-muted mb-3">
          Pre-fetch prior-week BasePlan into <code>prev_baseline_latest.parquet</code> before running the engine (Streamlit parity on Configure step).
        </p>
        <div className="grid-2 mb-3" style={{ maxWidth: 400 }}>
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
        <button
          type="button"
          className="btn btn-secondary"
          disabled={readOnly || fetchingPrev}
          onClick={fetchPrevious}
        >
          <RefreshCw size={14} className={fetchingPrev ? "animate-spin" : ""} />
          {fetchingPrev ? "Fetching…" : "Fetch Previous Baseline"}
        </button>
        {prevPreview && (
          <p className="text-sm mt-3">
            Loaded <strong>{Number(prevPreview.rows || 0).toLocaleString()}</strong> rows · BasePlan sum{" "}
            {Number(prevPreview.base_plan_sum || 0).toLocaleString()}
          </p>
        )}
      </SectionCard>
    </BaselineStepShell>
  );
}

export default function ConfigurePage() {
  return (
    <Suspense>
      <ConfigureContent />
    </Suspense>
  );
}
