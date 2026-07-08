"use client";

import { useEffect, useState, useCallback, useMemo, useRef, type MutableRefObject } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import FilterChipSelect from "@/components/ui/FilterChipSelect";
import BufferHeatmapChart from "@/components/charts/BufferHeatmapChart";
import RevenueTrendChart from "@/components/charts/RevenueTrendChart";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { cacheGet, cacheInvalidate, cacheSet } from "@/lib/queryCache";
import { coerceNum } from "@/lib/coerceNum";
import {
  RefreshCw, ExternalLink, AlertTriangle, ChevronDown, ChevronUp,
  TrendingUp, BarChart3, Package, Building2, MapPin,
} from "lucide-react";

function deltaCellStyle(v: unknown): React.CSSProperties {
  const n = coerceNum(v);
  if (n == null) return { color: "var(--text-muted)" };
  if (n >= 10) return { background: "rgba(16,185,129,0.25)", color: "#10b981", fontWeight: 600 };
  if (n > 0) return { background: "rgba(16,185,129,0.1)", color: "#10b981" };
  if (n <= -10) return { background: "rgba(239,68,68,0.25)", color: "#ef4444", fontWeight: 600 };
  if (n < 0) return { background: "rgba(239,68,68,0.1)", color: "#ef4444" };
  return { background: "var(--bg-elevated)", color: "var(--text-muted)" };
}

function fmtDelta(v: unknown): string {
  const n = coerceNum(v);
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

type PivotTable = { label_col: string; columns: string[]; rows: Record<string, unknown>[] };

function DeltaTable({ table, labelCol }: { table: PivotTable; labelCol: string }) {
  return (
    <div className="table-wrap dashboard-table-scroll">
      <table className="delta-table">
        <thead>
          <tr>
            {table.columns.map(c => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i}>
              {table.columns.map(c => {
                const v = row[c];
                const isLabel = c === labelCol;
                return (
                  <td
                    key={c}
                    style={isLabel ? { fontWeight: 600, whiteSpace: "nowrap" } : deltaCellStyle(v)}
                  >
                    {isLabel ? String(v ?? "") : fmtDelta(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SimpleTable({ columns, rows }: { columns: string[]; rows: Record<string, unknown>[] }) {
  if (!rows.length) return <div className="text-xs text-muted">No data.</div>;
  return (
    <div className="table-wrap dashboard-table-scroll">
      <table>
        <thead><tr>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map(c => (
                <td key={c} style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>{String(row[c] ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ViewRadio({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const opts = ["City", "Category", "City × Category"];
  return (
    <div className="view-radio-group">
      <div className="text-xs text-muted" style={{ marginBottom: "0.5rem" }}>{label}</div>
      <div className="view-radio-pills">
        {opts.map(o => (
          <button
            key={o}
            type="button"
            className={`view-radio-pill${value === o ? " active" : ""}`}
            onClick={() => onChange(o)}
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

function SectionHeader({ title, subtitle, icon }: { title: string; subtitle?: string; icon?: React.ReactNode }) {
  return (
    <div className="dashboard-section-header">
      {icon && <div className="dashboard-section-icon">{icon}</div>}
      <div>
        <h3 className="dashboard-section-title">{title}</h3>
        {subtitle && <p className="dashboard-section-sub">{subtitle}</p>}
      </div>
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="chart-skeleton">
      <div className="chart-skeleton-bars" />
    </div>
  );
}

function trendQuery(
  selCities: string[],
  selCats: string[],
  selDays: string[],
  dodView: string,
  wowView: string,
) {
  const params = new URLSearchParams();
  if (selCities.length) params.set("cities", selCities.join(","));
  if (selCats.length) params.set("categories", selCats.join(","));
  if (selDays.length) params.set("days", selDays.join(","));
  params.set("dod_view", dodView);
  params.set("wow_view", wowView);
  return params.toString();
}

const DEFAULT_CITIES_COUNT = 3;
const DASHBOARD_BOOTSTRAP_KEY = "dashboard:bootstrap";

type DashboardBootstrap = {
  pipeline_card: { has_run: boolean; run_name?: string; status?: string };
  weeks: { weeks?: string[]; default_week?: string };
  analytics: Record<string, unknown>;
  revenue_trends: Record<string, unknown>;
  data_warning?: string;
};

function applyBootstrapPayload(
  data: DashboardBootstrap,
  setters: {
    setPipelineCard: (v: DashboardBootstrap["pipeline_card"]) => void;
    setWeeks: (v: string[]) => void;
    setSelectedWeek: (v: string) => void;
    setAnalytics: (v: Record<string, unknown>) => void;
    setTrends: (v: Record<string, unknown>) => void;
    setSelCities: (v: string[]) => void;
    setFiltersReady: (v: boolean) => void;
    filtersInit: MutableRefObject<boolean>;
    skipTrendsFetch: MutableRefObject<boolean>;
  },
) {
  const wkList = data.weeks?.weeks || [];
  setters.setPipelineCard(data.pipeline_card);
  setters.setWeeks(wkList);
  setters.setSelectedWeek(data.weeks?.default_week || wkList[wkList.length - 1] || "");
  setters.setAnalytics(data.analytics);
  setters.setTrends(data.revenue_trends);
  const initialCities = (
    (data.revenue_trends?.filters as { all_cities?: string[] } | undefined)?.all_cities || []
  ).slice(0, DEFAULT_CITIES_COUNT);
  if (initialCities.length && !setters.filtersInit.current) {
    setters.setSelCities(initialCities);
    setters.filtersInit.current = true;
  }
  setters.setFiltersReady(true);
  setters.skipTrendsFetch.current = true;
}

export default function DashboardPage() {
  const { user, hydrated, role } = useAuth();
  const [pipelineCard, setPipelineCard] = useState<{ has_run: boolean; run_name?: string; status?: string } | null>(null);
  const [weeks, setWeeks] = useState<string[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string>("");
  const [analytics, setAnalytics] = useState<any>(null);
  const [shellLoading, setShellLoading] = useState(true);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [error, setError] = useState("");
  const [dataWarning, setDataWarning] = useState("");
  const [trends, setTrends] = useState<any>(null);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [selCities, setSelCities] = useState<string[]>([]);
  const [selCats, setSelCats] = useState<string[]>([]);
  const [selDays, setSelDays] = useState<string[]>([]);
  const [dodView, setDodView] = useState("City");
  const [wowView, setWowView] = useState("City");
  const [showDodTable, setShowDodTable] = useState(false);
  const [showWowTable, setShowWowTable] = useState(false);
  const [filtersReady, setFiltersReady] = useState(false);
  const [opsReady, setOpsReady] = useState(false);

  const skipTrendsFetch = useRef(false);
  const filtersInit = useRef(false);
  const bootstrapSeq = useRef(0);

  const bootstrapSetters = useMemo(
    () => ({
      setPipelineCard,
      setWeeks,
      setSelectedWeek,
      setAnalytics,
      setTrends,
      setSelCities,
      setFiltersReady,
      filtersInit,
      skipTrendsFetch,
    }),
    [],
  );

  const applyBootstrap = useCallback(
    (data: DashboardBootstrap) => applyBootstrapPayload(data, bootstrapSetters),
    [bootstrapSetters],
  );

  const loadTrends = useCallback(async (
    cities: string[],
    cats: string[],
    days: string[],
    dod: string,
    wow: string,
  ) => {
    setTrendsLoading(true);
    try {
      const q = trendQuery(cities, cats, days, dod, wow);
      const { data } = await api.get(`/api/dashboard/revenue-trends?${q}`);
      setTrends(data);
    } catch {
      setTrends({ empty: true });
    }
    setTrendsLoading(false);
  }, []);

  const loadWeekAnalytics = useCallback(async (week: string) => {
    if (!week) return;
    setAnalyticsLoading(true);
    try {
      const { data } = await api.get(`/api/dashboard/analytics?week=${encodeURIComponent(week)}`);
      setAnalytics(data);
      setError("");
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load week analytics");
    }
    setAnalyticsLoading(false);
  }, []);

  const initDashboard = useCallback(async (background = false) => {
    const seq = ++bootstrapSeq.current;
    if (!background) {
      const cached = cacheGet<DashboardBootstrap>(DASHBOARD_BOOTSTRAP_KEY);
      if (cached) {
        applyBootstrap(cached);
        setShellLoading(false);
        setError("");
      } else {
        setShellLoading(true);
      }
    }

    try {
      const { data } = await api.get<DashboardBootstrap>("/api/dashboard/bootstrap");
      if (seq !== bootstrapSeq.current) return;
      cacheSet(DASHBOARD_BOOTSTRAP_KEY, data, 300_000);
      applyBootstrap(data);
      setDataWarning(data.data_warning || "");
      setError("");
    } catch (e: unknown) {
      if (seq !== bootstrapSeq.current) return;
      const err = e as { response?: { data?: { detail?: string } } };
      if (!cacheGet(DASHBOARD_BOOTSTRAP_KEY)) {
        setError(err?.response?.data?.detail || "Failed to load dashboard");
      }
    } finally {
      if (seq === bootstrapSeq.current) {
        setShellLoading(false);
        setAnalyticsLoading(false);
        setTrendsLoading(false);
      }
    }
  }, [applyBootstrap]);

  useEffect(() => {
    initDashboard(false);
  }, [initDashboard]);

  useEffect(() => {
    const timer = window.setTimeout(() => setOpsReady(true), 400);
    return () => window.clearTimeout(timer);
  }, []);

  const handleRefresh = () => {
    cacheInvalidate(DASHBOARD_BOOTSTRAP_KEY);
    initDashboard(false);
  };

  const handleWeekChange = (week: string) => {
    setSelectedWeek(week);
    cacheInvalidate(DASHBOARD_BOOTSTRAP_KEY);
    loadWeekAnalytics(week);
  };

  useEffect(() => {
    if (!filtersReady) return;
    if (skipTrendsFetch.current) {
      skipTrendsFetch.current = false;
      return;
    }
    const timer = setTimeout(
      () => loadTrends(selCities, selCats, selDays, dodView, wowView),
      350,
    );
    return () => clearTimeout(timer);
  }, [selCities, selCats, selDays, dodView, wowView, filtersReady, loadTrends]);

  const roleLabel = role.charAt(0).toUpperCase() + role.slice(1);

  const deltaTabs = useMemo(() => analytics && !analytics.empty ? [
    { id: "city-date", label: "City × Date", content: <DeltaTable table={analytics.delta_city_date} labelCol="City" /> },
    { id: "city-cat-date", label: "City × Category × Date", content: <DeltaTable table={analytics.delta_city_cat_date} labelCol="City · Category" /> },
  ] : [], [analytics]);

  const newProdTabs = useMemo(() => analytics?.new_additions ? [
    { id: "by-product", label: "By Product", content: <SimpleTable columns={["Product", "Category", "Plan Revenue", "Plan Qty"]} rows={analytics.new_additions.new_products.by_product} /> },
    { id: "by-city", label: "By City", content: <SimpleTable columns={["City", "Product", "Plan Revenue", "Plan Qty"]} rows={analytics.new_additions.new_products.by_city} /> },
    { id: "by-category", label: "By Category", content: <SimpleTable columns={["Category", "Product", "Plan Revenue", "Plan Qty"]} rows={analytics.new_additions.new_products.by_category} /> },
  ] : [], [analytics]);

  const showAnalytics = analytics && !analytics.empty;
  const pipelineStatusClass = pipelineCard?.status === "Success"
    ? "status-success"
    : pipelineCard?.status === "Failed"
      ? "status-failed"
      : pipelineCard?.status === "In progress"
        ? "status-running"
        : "";

  return (
    <AppShell
      title="Dashboard"
      subtitle="Weekly planning analytics & revenue trends"
      actions={
        <button className="btn btn-secondary btn-sm" onClick={handleRefresh} disabled={shellLoading || analyticsLoading}>
          <RefreshCw size={13} className={shellLoading || analyticsLoading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {hydrated && user && (
        <div className="welcome-strip">
          Welcome back, <strong>{user.full_name || user.email}</strong>.
          You are signed in as <strong>{roleLabel}</strong>.
        </div>
      )}

      <div className="dashboard-pipeline-card card">
        <div className="dashboard-pipeline-top">
          <div>
            <div className="stat-label">Pipeline</div>
            <div className="dashboard-pipeline-title">
              {pipelineCard?.has_run ? pipelineCard.run_name : "No pipeline run yet"}
            </div>
          </div>
          <Link href="/autopilot" className="btn btn-primary btn-sm">
            <ExternalLink size={13} /> Open Auto-Pilot
          </Link>
        </div>
        <div className="dashboard-pipeline-meta">
          <div>
            <span className="text-xs text-muted">Status</span>
            <div className={`dashboard-status-pill ${pipelineStatusClass}`}>
              {pipelineCard?.has_run ? pipelineCard.status : "—"}
            </div>
          </div>
          {weeks.length > 0 && (
            <div className="dashboard-week-picker">
              <label className="text-xs text-muted">View week</label>
              <select
                className="input"
                value={selectedWeek}
                onChange={e => handleWeekChange(e.target.value)}
                disabled={analyticsLoading}
              >
                {weeks.map(w => <option key={w} value={w}>{w}</option>)}
              </select>
            </div>
          )}
        </div>
      </div>

      {dataWarning && (
        <div className="alert alert-warning dashboard-error" style={{ whiteSpace: "pre-wrap" }}>
          <strong>6-week dashboard data not available.</strong>
          <div className="text-sm mt-2">{dataWarning}</div>
          <div className="text-sm mt-2">
            Run <a href="/baseline/load-raw" className="font-semibold underline">Manual Baseline → Load Raw Data</a> once,
            or mount the planning drive CSV, then refresh.
          </div>
        </div>
      )}

      {error && (
        <div className="alert alert-danger dashboard-error">{error}</div>
      )}

      {shellLoading && (
        <div className="dashboard-loading-shell">
          <span className="spinner" style={{ width: 28, height: 28 }} />
          <div className="text-xs text-muted">Loading dashboard…</div>
        </div>
      )}

      {!shellLoading && analyticsLoading && !showAnalytics && (
        <div className="dashboard-loading-shell">
          <span className="spinner" style={{ width: 24, height: 24 }} />
          <div className="text-xs text-muted">Loading week analytics…</div>
        </div>
      )}

      {showAnalytics && (
        <>
          <div className="week-badges">
            <span className="week-badge week-badge-primary">
              {analytics.week_label} · {analytics.week_range.start} – {analytics.week_range.end}
            </span>
            {analytics.prev_week_label && (
              <span className="week-badge week-badge-compare">vs {analytics.prev_week_label}</span>
            )}
            {!analytics.prev_available && (
              <span className="week-badge week-badge-warn">
                <AlertTriangle size={12} style={{ display: "inline", marginRight: 4 }} />
                No prior week — new hub/product view unavailable
              </span>
            )}
            {analyticsLoading && (
              <span className="text-xs text-muted" style={{ marginLeft: "auto" }}>Updating…</span>
            )}
          </div>

          <div className="stat-grid dashboard-kpi-grid">
            {[
              { label: "Total Plan (Packets)", value: analytics.kpis.total_plan_qty.toLocaleString("en-IN", { maximumFractionDigits: 0 }), icon: <Package size={16} /> },
              { label: "Total Plan Revenue", value: `₹${analytics.kpis.total_plan_rev.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`, icon: <TrendingUp size={16} /> },
              { label: "Cities", value: analytics.kpis.n_cities, icon: <MapPin size={16} /> },
              { label: "Active Hubs", value: analytics.kpis.n_hubs, icon: <Building2 size={16} /> },
              { label: "Active SKUs", value: analytics.kpis.n_skus, icon: <BarChart3 size={16} /> },
            ].map(s => (
              <div className="stat-card dashboard-kpi-card" key={s.label}>
                <div className="dashboard-kpi-icon">{s.icon}</div>
                <div className="stat-label">{s.label}</div>
                <div className="stat-value">{s.value}</div>
              </div>
            ))}
          </div>

          <section className="dashboard-section card">
            <SectionHeader
              title="Plan / Baseline Delta %"
              subtitle="(r7_plan_rev / BaseRev − 1) × 100 — green above baseline, red below"
              icon={<BarChart3 size={18} />}
            />
            <Tabs tabs={deltaTabs} />
          </section>

          <section className="dashboard-section card">
            <SectionHeader
              title="Inventory Buffer"
              subtitle="r7_inv vs r7_plan by City × Category — % buffer or shortfall"
              icon={<Package size={18} />}
            />
            {analytics.inventory_buffer.available ? (
              <BufferHeatmapChart
                cities={analytics.inventory_buffer.cities}
                categories={analytics.inventory_buffer.categories}
                values={analytics.inventory_buffer.values}
              />
            ) : (
              <div className="alert alert-warning text-xs">No inventory buffer data for this week.</div>
            )}
          </section>

          <section className="dashboard-section card">
            <SectionHeader
              title={`New Additions · ${analytics.week_label}`}
              subtitle={analytics.prev_week_label ? `Compared with ${analytics.prev_week_label}` : undefined}
              icon={<TrendingUp size={18} />}
            />
            {!analytics.new_additions.prev_available ? (
              <div className="alert alert-warning text-xs">No prior week data — comparison unavailable.</div>
            ) : (
              <div className="dashboard-split-grid">
                <div className="dashboard-subcard">
                  <div className="dashboard-subcard-title">
                    New Hubs ({analytics.new_additions.new_hub_count})
                  </div>
                  {analytics.new_additions.new_hub_count === 0 ? (
                    <div className="text-xs text-muted">No new hubs since {analytics.prev_week_label}.</div>
                  ) : (
                    <SimpleTable columns={["Hub", "City", "Plan Revenue", "Plan Qty"]} rows={analytics.new_additions.new_hubs} />
                  )}
                </div>
                <div className="dashboard-subcard">
                  <div className="dashboard-subcard-title">
                    New Products ({analytics.new_additions.new_product_count})
                  </div>
                  {analytics.new_additions.new_product_count === 0 ? (
                    <div className="text-xs text-muted">No new products with r7_plan &gt; 0 since {analytics.prev_week_label}.</div>
                  ) : (
                    <Tabs tabs={newProdTabs} />
                  )}
                </div>
              </div>
            )}
          </section>
        </>
      )}

      {!shellLoading && analytics?.empty && (
        <div className="alert alert-warning">No data found in the 6-week rolling file.</div>
      )}

      {!shellLoading && (
        <section className="dashboard-section card dashboard-trends-section">
          <SectionHeader
            title="City Category Revenue Trends"
            subtitle="Actual (solid) vs Plan (dashed) · Last 10 ISO weeks"
            icon={<TrendingUp size={18} />}
          />

          {trendsLoading && !trends ? (
            <ChartSkeleton />
          ) : trends?.empty ? (
            <div className="alert alert-warning text-xs">{trends.message || "No trend data available."}</div>
          ) : trends ? (
            <>
              <div className="dashboard-filters card" style={{ padding: "1rem", marginBottom: "1.25rem", background: "var(--bg-elevated)" }}>
                <div className="grid-3">
                  <FilterChipSelect
                    label="City"
                    options={trends.filters?.all_cities || []}
                    selected={selCities}
                    onChange={setSelCities}
                    placeholder="Filter cities…"
                  />
                  <FilterChipSelect
                    label="Category"
                    options={trends.filters?.all_categories || []}
                    selected={selCats}
                    onChange={setSelCats}
                    placeholder="Filter categories…"
                  />
                  <FilterChipSelect
                    label="Day of week"
                    options={trends.filters?.all_days || []}
                    selected={selDays}
                    onChange={setSelDays}
                    placeholder="Filter days…"
                  />
                </div>
              </div>

              {trendsLoading && (
                <div className="text-xs text-muted" style={{ marginBottom: "0.75rem" }}>Updating charts…</div>
              )}

              <div className="dashboard-chart-block">
                <h4 className="dashboard-chart-heading">Day-on-Day — Last 10 Weeks</h4>
                {trends.day_on_day?.empty ? (
                  <div className="alert alert-warning text-xs">No data for the selected filters.</div>
                ) : trends.day_on_day?.chart ? (
                  <div className="chart-card">
                    <ViewRadio label="Break down by" value={dodView} onChange={setDodView} />
                    {trendsLoading ? <ChartSkeleton /> : <RevenueTrendChart chart={trends.day_on_day.chart} />}
                    <button type="button" className="btn btn-secondary btn-sm chart-table-toggle" onClick={() => setShowDodTable(v => !v)}>
                      {showDodTable ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      {showDodTable ? "Hide" : "Show"} data table
                    </button>
                    {showDodTable && (
                      <SimpleTable columns={["Date", "Day", "City", "Category", "Actual Revenue", "Plan Revenue"]} rows={trends.day_on_day.table} />
                    )}
                  </div>
                ) : null}
              </div>

              <div className="dashboard-chart-block">
                <h4 className="dashboard-chart-heading">Week-on-Week — Last 10 Weeks</h4>

                {trends.week_on_week?.latest_metrics && (
                  <div className="stat-grid" style={{ marginBottom: "1rem" }}>
                    <div className="stat-card">
                      <div className="stat-label">Latest Week</div>
                      <div className="stat-value" style={{ fontSize: "1.2rem" }}>{trends.week_on_week.latest_metrics.latest_week}</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-label">Actual Revenue</div>
                      <div className="stat-value" style={{ fontSize: "1.2rem" }}>
                        ₹{trends.week_on_week.latest_metrics.actual_revenue.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                      </div>
                      <div className="stat-sub">
                        {(() => {
                          const pct = coerceNum(trends.week_on_week.latest_metrics.pct_vs_plan);
                          if (pct == null) return "— vs Plan";
                          return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% vs Plan`;
                        })()}
                      </div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-label">Plan Revenue</div>
                      <div className="stat-value" style={{ fontSize: "1.2rem" }}>
                        ₹{trends.week_on_week.latest_metrics.plan_revenue.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                      </div>
                    </div>
                  </div>
                )}

                {trends.week_on_week?.empty ? (
                  <div className="alert alert-warning text-xs">No data for the selected filters.</div>
                ) : trends.week_on_week?.chart ? (
                  <div className="chart-card">
                    <ViewRadio label="Week breakdown by" value={wowView} onChange={setWowView} />
                    {trendsLoading ? <ChartSkeleton /> : <RevenueTrendChart chart={trends.week_on_week.chart} />}
                    <button type="button" className="btn btn-secondary btn-sm chart-table-toggle" onClick={() => setShowWowTable(v => !v)}>
                      {showWowTable ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      {showWowTable ? "Hide" : "Show"} data table
                    </button>
                    {showWowTable && (
                      <SimpleTable columns={["Week", "City", "Category", "Actual Revenue", "Plan Revenue"]} rows={trends.week_on_week.table} />
                    )}
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </section>
      )}

      {opsReady && <DashboardOpsPanels />}
    </AppShell>
  );
}

function DashboardOpsPanels() {
  const [pipeline, setPipeline] = useState<{ steps?: Record<string, unknown>[] } | null>(null);
  const [baselineRuns, setBaselineRuns] = useState<Record<string, unknown>[]>([]);
  const [fpRuns, setFpRuns] = useState<Record<string, unknown>[]>([]);
  const [emails, setEmails] = useState<Record<string, unknown>[]>([]);
  const [auditing, setAuditing] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get("/api/dashboard/pipeline-flow"),
      api.get("/api/dashboard/baseline-runs"),
      api.get("/api/dashboard/final-plan-runs"),
      api.get("/api/dashboard/email-log"),
    ])
      .then(([p, b, f, e]) => {
        setPipeline(p.data);
        setBaselineRuns(b.data);
        setFpRuns(f.data);
        setEmails(e.data);
      })
      .catch(() => {});
  }, [auditing]);

  const runAudit = async () => {
    setAuditing(true);
    try {
      await api.post("/api/dashboard/pipeline-flow/run");
    } catch {
      /* ignore */
    }
    setAuditing(false);
  };

  return (
    <>
      <section className="dashboard-section card mt-4">
        <SectionHeader title="Pipeline Flow" subtitle="7-step audit status" icon={<BarChart3 size={18} />} />
        <button type="button" className="btn btn-secondary btn-sm mb-3" onClick={runAudit} disabled={auditing}>
          {auditing ? "Running audit…" : "Run pipeline audit"}
        </button>
        {pipeline?.steps && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Step</th>
                  <th>Status</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {(pipeline.steps as Record<string, unknown>[]).map((s, i) => (
                  <tr key={i}>
                    <td>{String(s.name ?? s.step ?? i + 1)}</td>
                    <td>{String(s.status ?? "—")}</td>
                    <td style={{ fontSize: "0.72rem" }}>{String(s.message ?? s.detail ?? "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="dashboard-section card mt-4">
        <SectionHeader title="Recent Runs" subtitle="Baseline & Final Plan" icon={<Package size={18} />} />
        <div className="grid-2">
          <div>
            <h4 className="text-sm font-semibold mb-2">Baseline</h4>
            <SimpleTable
              columns={["run_name", "status", "run_date"]}
              rows={baselineRuns.slice(0, 5) as Record<string, unknown>[]}
            />
          </div>
          <div>
            <h4 className="text-sm font-semibold mb-2">Final Plan</h4>
            <SimpleTable
              columns={["run_name", "status", "run_date"]}
              rows={fpRuns.slice(0, 5) as Record<string, unknown>[]}
            />
          </div>
        </div>
      </section>

      <section className="dashboard-section card mt-4 mb-4">
        <SectionHeader title="Email Log" subtitle="Recent notifications" icon={<AlertTriangle size={18} />} />
        <SimpleTable
          columns={["sent_at", "email_type", "subject", "status"]}
          rows={emails.slice(0, 10) as Record<string, unknown>[]}
        />
      </section>
    </>
  );
}
