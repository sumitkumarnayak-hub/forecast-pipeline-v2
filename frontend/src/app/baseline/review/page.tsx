"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
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

function ComparisonPanel({ view }: { view: string }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ComparisonData | null>(null);
  const [msg, setMsg] = useState("");

  const load = useCallback(
    async (refresh = false) => {
      setLoading(true);
      setMsg("");
      try {
        const { data: res } = await api.get("/api/baseline/review/comparison", {
          params: { view, refresh },
        });
        setData(res);
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
  return (
    <>
      {(data.current_file || data.previous_file) && (
        <p className="text-xs text-muted mb-3">
          Current: <strong>{data.current_file || "—"}</strong>
          {" · "}
          Previous: <strong>{data.previous_file || "—"}</strong>
          {" · "}
          {data.row_count ?? data.rows.length} rows
        </p>
      )}
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
            {data.rows.map((row, i) => (
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
      <button type="button" className="btn btn-secondary btn-sm mt-3" onClick={() => load(true)}>
        <RefreshCw size={13} /> Rebuild comparison cache
      </button>
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

      <SectionCard title="Multi-level Comparison">
        <UrlTabs param="view" defaultTab="city-day" tabs={comparisonTabs} />
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
