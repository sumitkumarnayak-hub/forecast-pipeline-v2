"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import BaselineStepShell from "@/components/baseline/BaselineStepShell";
import SectionCard from "@/components/baseline/SectionCard";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { CheckCircle, ChevronRight, RefreshCw, ThumbsDown, ThumbsUp, XCircle } from "lucide-react";

interface HubSuggestionData {
  source?: string;
  metrics?: {
    total_base_plan: number;
    unique_groups: number;
    sku_classes: number;
    hubs: number;
  };
  filters?: {
    group_label: string;
    cities: string[];
    sku_classes: string[];
  };
  day_totals?: Record<string, number>;
  pivot_columns?: string[];
  pivot_rows?: Record<string, unknown>[];
}

export default function ApprovePage() {
  const { readOnly, canApprove } = useAuth();
  const [status, setStatus] = useState<{ approved?: boolean } | null>(null);
  const [hubData, setHubData] = useState<HubSuggestionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [hubLoading, setHubLoading] = useState(false);
  const [acting, setActing] = useState("");
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [cityFilter, setCityFilter] = useState("All");
  const [skuFilter, setSkuFilter] = useState("All");

  const loadStatus = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/baseline/status");
      setStatus(data);
    } catch {
      setStatus(null);
    }
    setLoading(false);
  };

  const loadHub = useCallback(
    async (refresh = false) => {
      setHubLoading(true);
      try {
        const { data } = await api.get("/api/baseline/approve/hub-suggestion", {
          params: { refresh, city_filter: cityFilter, sku_filter: skuFilter },
        });
        setHubData(data);
        setMsg({ text: "", type: "" });
      } catch (e: unknown) {
        const err = e as { response?: { data?: { detail?: string } } };
        setMsg({ text: err?.response?.data?.detail || "Failed to load hub suggestion", type: "danger" });
      } finally {
        setHubLoading(false);
      }
    },
    [cityFilter, skuFilter],
  );

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    if (hubData) loadHub();
  }, [cityFilter, skuFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const doApprove = async () => {
    setActing("approve");
    try {
      const { data } = await api.post("/api/baseline/approve");
      setMsg({ text: data.detail, type: "success" });
      loadStatus();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Error", type: "danger" });
    }
    setActing("");
  };

  const doReject = async () => {
    setActing("reject");
    try {
      const { data } = await api.post("/api/baseline/reject");
      setMsg({ text: data.detail, type: "warning" });
      loadStatus();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Error", type: "danger" });
    }
    setActing("");
  };

  const m = hubData?.metrics;
  const groupLabel = hubData?.filters?.group_label || "City";
  const pivotCols = hubData?.pivot_columns || [];
  const pivotRows = hubData?.pivot_rows || [];

  return (
    <BaselineStepShell
      stepId="approve"
      actions={
        <button type="button" className="btn btn-secondary btn-sm" onClick={loadStatus} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {readOnly && (
        <div className="alert alert-info text-sm mb-4">
          Read-only access — approval is disabled for your role.
        </div>
      )}

      {msg.text && <div className={`alert alert-${msg.type} mb-4`}>{msg.text}</div>}

      {!loading && status?.approved && (
        <div className="alert alert-success mb-4 text-sm">
          <CheckCircle size={15} /> Baseline approved — Final Plan is unlocked from the sidebar.
        </div>
      )}

      <SectionCard
        title="City × Category × Day — Base Plan View"
        description="Load Hub level Suggestion sheet for pivot review before approval."
      >
        <button
          type="button"
          className="btn btn-secondary btn-sm mb-4"
          disabled={readOnly || hubLoading}
          onClick={() => loadHub(true)}
        >
          <RefreshCw size={13} className={hubLoading ? "animate-spin" : ""} /> Load / Refresh
        </button>
        <div className="stat-grid grid-4 mb-4">
          <div className="stat-card">
            <div className="stat-label">Total Base Plan</div>
            <div className="stat-value">{m ? m.total_base_plan.toLocaleString() : "—"}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">{groupLabel}s</div>
            <div className="stat-value">{m ? m.unique_groups : "—"}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Hubs</div>
            <div className="stat-value">{m ? m.hubs : "—"}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">SKU Classes</div>
            <div className="stat-value">{m ? m.sku_classes : "—"}</div>
          </div>
        </div>
        <div className="grid-2 mb-4" style={{ maxWidth: 480 }}>
          <div className="form-group">
            <label className="form-label">{groupLabel} filter</label>
            <select
              className="form-input"
              value={cityFilter}
              onChange={e => setCityFilter(e.target.value)}
              disabled={!hubData}
            >
              {(hubData?.filters?.cities || ["All"]).map(c => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">SKU Class Prod</label>
            <select
              className="form-input"
              value={skuFilter}
              onChange={e => setSkuFilter(e.target.value)}
              disabled={!hubData}
            >
              {(hubData?.filters?.sku_classes || ["All"]).map(s => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>
        {hubLoading ? (
          <span className="spinner" />
        ) : pivotRows.length > 0 ? (
          <div className="table-wrap" style={{ maxHeight: 480, overflow: "auto" }}>
            <table>
              <thead>
                <tr>
                  {pivotCols.map(c => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pivotRows.map((row, i) => (
                  <tr key={i}>
                    {pivotCols.map(c => (
                      <td key={c} style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }}>
                        {String(row[c] ?? "—")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs text-muted">Pivot table (Mon–Sun + Total) appears after sheet load.</p>
        )}
      </SectionCard>

      <SectionCard title="Approve &amp; Unlock Final Plan">
        {!loading && status && (
          <div className={`alert ${status.approved ? "alert-success" : "alert-warning"} mb-4`}>
            {status.approved ? (
              <>
                <CheckCircle size={15} /> Baseline is <strong>approved</strong>.
              </>
            ) : (
              <>
                <XCircle size={15} /> Baseline not yet approved — admin must approve before Final Plan.
              </>
            )}
          </div>
        )}

        {canApprove ? (
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-success"
              onClick={doApprove}
              disabled={!!acting || status?.approved || readOnly}
            >
              {acting === "approve" ? (
                <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
              ) : (
                <ThumbsUp size={13} />
              )}{" "}
              Approve Baseline
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={doReject}
              disabled={!!acting || !status?.approved || readOnly}
            >
              {acting === "reject" ? (
                <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
              ) : (
                <ThumbsDown size={13} />
              )}{" "}
              Revoke Approval
            </button>
          </div>
        ) : (
          <p className="text-sm text-muted">You do not have permission to approve the baseline.</p>
        )}
      </SectionCard>

      {status?.approved && (
        <div className="mt-8 flex justify-end border-t pt-6" style={{ borderColor: "var(--border)" }}>
          <Link href="/final-plan" className="btn btn-primary">
            Continue to Final Plan
            <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
      )}
    </BaselineStepShell>
  );
}
