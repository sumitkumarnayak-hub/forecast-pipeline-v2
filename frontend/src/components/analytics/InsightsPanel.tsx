"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import FilterChipSelect from "@/components/ui/FilterChipSelect";
import GenericHeatmap from "@/components/analytics/GenericHeatmap";
import { DualLineChart, StackedLossChart, SimpleBarChart } from "@/components/analytics/InsightCharts";
import api from "@/lib/api";
import { AlertTriangle } from "lucide-react";

type Bootstrap = {
  empty?: boolean;
  message?: string;
  weeks?: string[];
  default_week?: string;
  cities?: string[];
  insight_views?: { id: string; label: string }[];
  loss_sub_views?: { id: string; label: string }[];
  attainment_sub_views?: { id: string; label: string }[];
  wastage_sub_views?: { id: string; label: string }[];
};

function fmtInr(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(1)} Cr`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(1)} L`;
  if (a >= 1e3) return `${sign}₹${(a / 1e3).toFixed(1)} K`;
  return `${sign}₹${a.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function fmtPct(v: number | null | undefined, d = 1) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v.toFixed(d)}%`;
}

function PreviewTable({ columns, rows, maxCols = 10 }: { columns: string[]; rows: Record<string, unknown>[]; maxCols?: number }) {
  const cols = columns.slice(0, maxCols);
  if (!rows.length) return <p className="text-xs text-muted">No rows.</p>;
  return (
    <div className="table-wrap" style={{ maxHeight: 360 }}>
      <table>
        <thead>
          <tr>{cols.map(c => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((row, i) => (
            <tr key={i}>
              {cols.map(c => (
                <td key={c} style={{ fontSize: "0.72rem" }}>
                  {typeof row[c] === "number" ? Number(row[c]).toLocaleString("en-IN", { maximumFractionDigits: 2 }) : String(row[c] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function InsightsPanel() {
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [week, setWeek] = useState("");
  const [cities, setCities] = useState<string[]>([]);
  const [view, setView] = useState("executive");
  const [subView, setSubView] = useState("");
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewLoading, setViewLoading] = useState(false);

  const [oaThr, setOaThr] = useState(120);
  const [uaThr, setUaThr] = useState(80);
  const [minPlan, setMinPlan] = useState(500);
  const [topN, setTopN] = useState(20);
  const [granularity, setGranularity] = useState("Daily");
  const [paretoDim, setParetoDim] = useState("Hub");
  const [categoryFocus, setCategoryFocus] = useState("");
  const [minWastage, setMinWastage] = useState(500);

  useEffect(() => {
    api.get<Bootstrap>("/api/insights/bootstrap")
      .then(({ data }) => {
        setBoot(data);
        if (data.default_week) setWeek(data.default_week);
      })
      .catch(() => setBoot({ empty: true, message: "Failed to load insights metadata." }))
      .finally(() => setLoading(false));
  }, []);

  const subViews = useMemo(() => {
    if (view === "revenue_loss") return boot?.loss_sub_views || [];
    if (view === "attainment") return boot?.attainment_sub_views || [];
    if (view === "wastage") return boot?.wastage_sub_views || [];
    return [];
  }, [view, boot]);

  useEffect(() => {
    if (subViews.length && !subViews.find(s => s.id === subView)) {
      setSubView(subViews[0].id);
    }
  }, [subViews, subView]);

  const loadView = useCallback(async () => {
    if (!week) return;
    setViewLoading(true);
    try {
      const params = new URLSearchParams({
        insight_view: view,
        week,
        oa_thr: String(oaThr),
        ua_thr: String(uaThr),
        min_plan: String(minPlan),
        top_n: String(topN),
        granularity,
        pareto_dim: paretoDim,
        min_wastage: String(minWastage),
      });
      if (cities.length) params.set("cities", cities.join(","));
      if (subView && subViews.length) params.set("sub_view", subView);
      if (categoryFocus) params.set("category_focus", categoryFocus);
      const { data } = await api.get(`/api/insights/view?${params}`);
      setPayload(data);
    } catch {
      setPayload({ empty: true, message: "Failed to load insight view." });
    }
    setViewLoading(false);
  }, [week, cities, view, subView, oaThr, uaThr, minPlan, topN, granularity, paretoDim, categoryFocus, minWastage, subViews.length]);

  useEffect(() => {
    if (week) loadView();
  }, [week, cities, view, subView, oaThr, uaThr, minPlan, topN, granularity, paretoDim, categoryFocus, minWastage, loadView]);

  if (loading) return <span className="spinner" />;
  if (boot?.empty) {
    return (
      <div className="alert alert-warning">
        <AlertTriangle size={14} /> {boot.message || "6-week data unavailable."}
      </div>
    );
  }

  const kpis = payload?.kpis as Record<string, number> | undefined;

  const executiveContent = payload && view === "executive" && (
    <>
      <div className="stat-grid mb-4">
        {[
          ["Plan Revenue", fmtInr(kpis?.plan_revenue), "packets planned"],
          ["Actual Revenue", fmtInr(kpis?.actual_revenue), `${Number(kpis?.sales_qty || 0).toLocaleString()} sales`],
          ["Attainment", fmtPct(kpis?.attainment_pct), "sales ÷ plan"],
          ["Availability", fmtPct(kpis?.availability_pct), "flag ÷ instances"],
          ["Total Rev Loss", fmtInr(kpis?.total_rev_loss), "from loss sheet"],
          ["Demand Loss", fmtInr(kpis?.demand_loss), "demand-led"],
          ["Supply Loss", fmtInr(kpis?.supply_loss), "supply-led"],
          ["Wastage", fmtInr(kpis?.total_wastage), fmtPct(kpis?.wastage_pct_of_rev) + " of rev"],
        ].map(([label, val, sub]) => (
          <div key={String(label)} className="stat-card">
            <div className="stat-label">{label}</div>
            <div className="stat-value">{val}</div>
            <div className="stat-sub text-xs text-muted">{sub}</div>
          </div>
        ))}
      </div>
      <div className="grid-2 mb-4">
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Plan vs Actual — daily</div>
          <DualLineChart
            data={(payload.daily_plan_actual as { date: string; plan_rev: number; actual_rev: number }[]) || []}
            xKey="date"
            lines={[
              { key: "plan_rev", name: "Plan ₹", color: "#3B82F6", dashed: true },
              { key: "actual_rev", name: "Actual ₹", color: "#10B981" },
            ]}
          />
        </div>
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Demand vs Supply loss — daily</div>
          <StackedLossChart
            data={((payload.daily_loss as { date: string; demand: number; supply: number }[]) || []).map(d => ({
              label: d.date,
              demand: d.demand,
              supply: d.supply,
            }))}
          />
        </div>
      </div>
      <div className="card">
        <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Top cities — plan revenue & attainment</div>
        <PreviewTable
          columns={["city_name", "plan_rev", "actual", "attainment"]}
          rows={(payload.city_leaderboard as Record<string, unknown>[]) || []}
        />
      </div>
    </>
  );

  const lossContent = payload && view === "revenue_loss" && (
    <>
      {subView === "loss_theatre" && (
        <div className="card">
          <div className="flex gap-3 mb-3">
            <label className="text-xs">
              Granularity{" "}
              <select className="form-input form-input-sm" value={granularity} onChange={e => setGranularity(e.target.value)}>
                <option>Daily</option>
                <option>Weekly</option>
              </select>
            </label>
          </div>
          <StackedLossChart
            data={((payload.loss_theatre as { label: string; demand: number; supply: number }[]) || [])}
          />
        </div>
      )}
      {subView === "city_category" && (
        <div className="grid-2">
          <div className="card">
            <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>City × Category breakdown</div>
            <PreviewTable
              columns={["city_name", "category", "total", "demand", "supply"]}
              rows={(payload.city_category_rows as Record<string, unknown>[]) || []}
            />
          </div>
          <div className="card">
            <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Top cities by loss</div>
            <PreviewTable columns={["city_name", "total"]} rows={(payload.city_waterfall as Record<string, unknown>[]) || []} />
          </div>
        </div>
      )}
      {subView === "hub_rca" && (
        <>
          <div className="card mb-4">
            <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Severity — hub × category (₹)</div>
            <GenericHeatmap
              rows={((payload.severity_heatmap as { rows: string[] })?.rows) || []}
              columns={((payload.severity_heatmap as { columns: string[] })?.columns) || []}
              values={((payload.severity_heatmap as { values: number[][] })?.values) || []}
              format="inr"
            />
          </div>
          <div className="card">
            <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Action table</div>
            <PreviewTable columns={["hub_name", "category", "total", "demand", "supply", "demand_share"]} rows={(payload.action_table as Record<string, unknown>[]) || []} />
          </div>
        </>
      )}
      {subView === "avoidable_pareto" && (
        <div className="card">
          <div className="flex gap-3 mb-3">
            <label className="text-xs">
              Group by{" "}
              <select className="form-input form-input-sm" value={paretoDim} onChange={e => setParetoDim(e.target.value)}>
                <option>Hub</option>
                <option>Category</option>
              </select>
            </label>
          </div>
          <PreviewTable
            columns={[paretoDim === "Hub" ? "hub_name" : "category", "avoid", "unavoid", "total", "cum_pct"]}
            rows={(payload.pareto_rows as Record<string, unknown>[]) || []}
          />
        </div>
      )}
      {subView === "category_severity" && (
        <div className="card">
          <label className="text-xs mb-2 block">
            Category{" "}
            <select className="form-input" value={categoryFocus} onChange={e => setCategoryFocus(e.target.value)}>
              {((payload.categories as string[]) || []).map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          <PreviewTable columns={["hub_name", "total", "demand", "supply"]} rows={(payload.top_hubs as Record<string, unknown>[]) || []} />
        </div>
      )}
    </>
  );

  const attainmentContent = payload && view === "attainment" && (
    <>
      <div className="grid-2 mb-4">
        <label className="text-sm">OA threshold (≥) <input type="range" min={100} max={200} step={5} value={oaThr} onChange={e => setOaThr(Number(e.target.value))} /> {oaThr}%</label>
        <label className="text-sm">UA threshold (≤) <input type="range" min={30} max={100} step={5} value={uaThr} onChange={e => setUaThr(Number(e.target.value))} /> {uaThr}%</label>
      </div>
      {subView === "leaderboard" && (
        <div className="grid-2">
          <div className="card">
            <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Over-attaining hubs</div>
            <PreviewTable columns={["hub_name", "city_name", "attainment", "plan_rev"]} rows={(payload.oa_hubs as Record<string, unknown>[]) || []} />
          </div>
          <div className="card">
            <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Under-attaining hubs</div>
            <PreviewTable columns={["hub_name", "city_name", "attainment", "plan_rev"]} rows={(payload.ua_hubs as Record<string, unknown>[]) || []} />
          </div>
          <div className="card" style={{ gridColumn: "1 / -1" }}>
            <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>City roll-up</div>
            <SimpleBarChart data={(payload.city_roll_up as Record<string, unknown>[]) || []} xKey="city_name" yKey="attainment" color="#3B82F6" height={400} />
          </div>
        </div>
      )}
      {subView === "consistency" && (
        <div className="card">
          <GenericHeatmap
            rows={((payload.heatmap as { rows: string[] })?.rows) || []}
            columns={((payload.heatmap as { columns: string[] })?.columns) || []}
            values={((payload.heatmap as { values: number[][] })?.values) || []}
            format="pct"
          />
        </div>
      )}
      {subView === "quadrant" && (
        <div className="card">
          <PreviewTable columns={["hub_name", "city_name", "attainment", "rev_gap", "plan_rev"]} rows={(payload.scatter as Record<string, unknown>[]) || []} />
        </div>
      )}
      {subView === "category" && (
        <div className="card">
          <PreviewTable columns={["sub_category", "attainment", "plan_rev", "rev"]} rows={(payload.category_rows as Record<string, unknown>[]) || []} />
        </div>
      )}
      {subView === "trend" && (
        <div className="card">
          <PreviewTable columns={["date", "band", "pct"]} rows={(payload.band_trend as Record<string, unknown>[]) || []} />
        </div>
      )}
    </>
  );

  const wastageContent = payload && view === "wastage" && (
    <>
      {subView === "volume_matrix" && (
        <div className="grid-2">
          <div className="card">
            <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Absolute wastage ₹</div>
            <GenericHeatmap
              rows={((payload.absolute_heatmap as { rows: string[] })?.rows) || []}
              columns={((payload.absolute_heatmap as { columns: string[] })?.columns) || []}
              values={((payload.absolute_heatmap as { values: number[][] })?.values) || []}
              format="inr"
            />
          </div>
          <div className="card">
            <div style={{ fontWeight: 700, marginBottom: "0.5rem" }}>Wastage % of revenue</div>
            <GenericHeatmap
              rows={((payload.pct_heatmap as { rows: string[] })?.rows) || []}
              columns={((payload.pct_heatmap as { columns: string[] })?.columns) || []}
              values={((payload.pct_heatmap as { values: number[][] })?.values) || []}
              format="pct"
            />
          </div>
        </div>
      )}
      {subView === "hotspots" && (
        <>
          <div className="card mb-4">
            <label className="text-xs">Min wastage ₹ <input type="number" className="form-input form-input-sm" value={minWastage} onChange={e => setMinWastage(Number(e.target.value))} /></label>
            <GenericHeatmap
              rows={((payload.heatmap as { rows: string[] })?.rows) || []}
              columns={((payload.heatmap as { columns: string[] })?.columns) || []}
              values={((payload.heatmap as { values: number[][] })?.values) || []}
              format="inr"
            />
          </div>
          <div className="card">
            <PreviewTable columns={["hub_name", "sub_category", "wastage", "wastage_pct", "qty"]} rows={(payload.action_table as Record<string, unknown>[]) || []} />
          </div>
        </>
      )}
      {subView === "trend" && (
        <div className="card">
          <DualLineChart
            data={((payload.daily_trend as { process_dt: string; wastage: number }[]) || []).map(d => ({
              date: String(d.process_dt).slice(0, 10),
              wastage: d.wastage,
            }))}
            xKey="date"
            lines={[{ key: "wastage", name: "Wastage ₹", color: "#7C3AED" }]}
          />
        </div>
      )}
      {subView === "quality_expiry" && (
        <div className="card">
          <PreviewTable columns={["sub_category", "quality", "expiry", "quality_share_pct"]} rows={(payload.category_split as Record<string, unknown>[]) || []} />
        </div>
      )}
    </>
  );

  const hubHealthContent = payload && view === "hub_health" && (
    <div className="card">
      <label className="text-xs mb-2 block">Min plan (packets) <input type="number" className="form-input form-input-sm" value={minPlan} onChange={e => setMinPlan(Number(e.target.value))} /></label>
      <PreviewTable
        columns={["hub_name", "city_name", "attainment", "wastage_pct", "loss_pct", "plan_rev"]}
        rows={(payload.hubs as Record<string, unknown>[]) || []}
      />
    </div>
  );

  return (
    <div>
      <div className="card mb-4">
        <div className="grid-2" style={{ alignItems: "end" }}>
          <div className="form-group">
            <label className="form-label">Week</label>
            <select className="form-input" value={week} onChange={e => setWeek(e.target.value)}>
              {(boot?.weeks || []).map(w => (
                <option key={w} value={w}>{w}</option>
              ))}
            </select>
          </div>
          <FilterChipSelect
            label="City filter"
            options={boot?.cities || []}
            selected={cities}
            onChange={setCities}
            placeholder="All cities"
          />
        </div>
        {payload && (
          <p className="text-xs text-muted mt-2">
            {String(payload.week)} · {String((payload.week_range as Record<string, string>)?.start)} – {String((payload.week_range as Record<string, string>)?.end)}
            {" · "}{Number(payload.active_hubs).toLocaleString()} hubs · {Number(payload.active_skus).toLocaleString()} SKUs
            {payload.loss_note ? ` · ${String(payload.loss_note)}` : ""}
          </p>
        )}
      </div>

      <div className="card mb-4">
        <div className="view-radio-pills">
          {(boot?.insight_views || []).map(v => (
            <button
              key={v.id}
              type="button"
              className={`view-radio-pill${view === v.id ? " active" : ""}`}
              onClick={() => setView(v.id)}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {subViews.length > 0 && (
        <div className="card mb-4">
          <div className="view-radio-pills" style={{ flexWrap: "wrap" }}>
            {subViews.map(s => (
              <button
                key={s.id}
                type="button"
                className={`view-radio-pill${subView === s.id ? " active" : ""}`}
                onClick={() => setSubView(s.id)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {viewLoading && <span className="spinner mb-3" />}
      {payload?.empty && !viewLoading && (
        <div className="alert alert-warning text-sm">{String(payload.message || "No data.")}</div>
      )}

      {!viewLoading && executiveContent}
      {!viewLoading && lossContent}
      {!viewLoading && attainmentContent}
      {!viewLoading && wastageContent}
      {!viewLoading && hubHealthContent}
    </div>
  );
}
