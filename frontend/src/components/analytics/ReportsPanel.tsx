"use client";

import { useCallback, useEffect, useState } from "react";
import { UrlTabs } from "@/components/ui/UrlTabs";
import FilterChipSelect from "@/components/ui/FilterChipSelect";
import RevenueTrendChart from "@/components/charts/RevenueTrendChart";
import api from "@/lib/api";

const DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function fmt(dt: string | null) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export default function ReportsPanel() {
  const [report, setReport] = useState("baseline-summary");
  const [reportData, setReportData] = useState<Record<string, unknown> | null>(null);
  const [baselineRuns, setBaselineRuns] = useState<Record<string, unknown>[]>([]);
  const [fpRuns, setFpRuns] = useState<Record<string, unknown>[]>([]);
  const [downloads, setDownloads] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);

  const [trendCities, setTrendCities] = useState<string[]>([]);
  const [trendCats, setTrendCats] = useState<string[]>([]);
  const [trendDays, setTrendDays] = useState<string[]>([]);
  const [dodView, setDodView] = useState("City");
  const [wowView, setWowView] = useState("City");
  const [trends, setTrends] = useState<Record<string, unknown> | null>(null);
  const [avpGranularity, setAvpGranularity] = useState("city_category");

  const loadReport = useCallback(async (key: string) => {
    setLoading(true);
    try {
      if (key === "baseline-summary") {
        const { data } = await api.get("/api/insights/reports/baseline-summary");
        setReportData(data);
      } else if (key === "plan-comparison") {
        const { data } = await api.get("/api/insights/reports/plan-comparison");
        setReportData(data);
      } else if (key === "actual-vs-plan") {
        const { data } = await api.get(`/api/insights/reports/actual-vs-plan?granularity=${avpGranularity}`);
        setReportData(data);
      } else if (key === "city-revenue-trends") {
        const params = new URLSearchParams({ dod_view: dodView, wow_view: wowView });
        if (trendCities.length) params.set("cities", trendCities.join(","));
        if (trendCats.length) params.set("categories", trendCats.join(","));
        if (trendDays.length) params.set("days", trendDays.join(","));
        const { data } = await api.get(`/api/insights/reports/city-revenue-trends?${params}`);
        setTrends(data);
      } else if (key === "run-history") {
        const [b, f] = await Promise.all([
          api.get("/api/insights/reports/baseline-runs"),
          api.get("/api/insights/reports/final-plan-runs"),
        ]);
        setBaselineRuns(b.data);
        setFpRuns(f.data);
      } else if (key === "downloads") {
        const { data } = await api.get("/api/insights/reports/downloads");
        setDownloads(data.files || []);
      }
    } catch {
      setReportData(null);
      setTrends(null);
    }
    setLoading(false);
  }, [avpGranularity, dodView, wowView, trendCities, trendCats, trendDays]);

  useEffect(() => {
    loadReport(report);
  }, [report, loadReport]);

  return (
    <div>
      <div className="form-group" style={{ maxWidth: 360, marginBottom: "1.25rem" }}>
        <label className="form-label">Choose report</label>
        <select className="form-input" value={report} onChange={e => setReport(e.target.value)}>
          <option value="baseline-summary">Baseline Summary</option>
          <option value="plan-comparison">Plan Comparison</option>
          <option value="actual-vs-plan">Actual vs Plan</option>
          <option value="city-revenue-trends">City Revenue Trends</option>
          <option value="run-history">Run History</option>
          <option value="downloads">Download Reports</option>
        </select>
      </div>

      {loading && <span className="spinner mb-3" />}

      {report === "baseline-summary" && reportData?.available ? (
        <div className="card">
          <p className="text-sm mb-2">
            <strong>{String(reportData.file)}</strong> — {Number(reportData.rows).toLocaleString()} rows
          </p>
          <div className="stat-grid mb-3">
            {Object.entries((reportData.metrics as Record<string, number>) || {}).map(([k, v]) => (
              <div key={k} className="stat-card">
                <div className="stat-label">{k}</div>
                <div className="stat-value">{Number(v).toLocaleString()}</div>
              </div>
            ))}
          </div>
          <div className="table-wrap" style={{ maxHeight: 360 }}>
            <table>
              <thead>
                <tr>
                  {((reportData.columns as string[]) || []).slice(0, 10).map(c => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {((reportData.preview_rows as Record<string, unknown>[]) || []).slice(0, 40).map((row, i) => (
                  <tr key={i}>
                    {((reportData.columns as string[]) || []).slice(0, 10).map(c => (
                      <td key={c} style={{ fontSize: "0.72rem" }}>{String(row[c] ?? "—")}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {report === "plan-comparison" && reportData && (
        <div className="card text-sm">
          <p className="text-muted">{String(reportData.message)}</p>
          <ul className="mt-2">
            {((reportData.summaries as { name: string; path?: string }[]) || []).map(s => (
              <li key={s.name}>{s.name}</li>
            ))}
          </ul>
        </div>
      )}

      {report === "actual-vs-plan" && (
        <>
          <div className="form-group mb-3" style={{ maxWidth: 280 }}>
            <label className="form-label">Granularity</label>
            <select className="form-input" value={avpGranularity} onChange={e => setAvpGranularity(e.target.value)}>
              <option value="city">City</option>
              <option value="category">Category</option>
              <option value="city_category">City + Category</option>
              <option value="city_category_hub">City + Category + Hub</option>
              <option value="city_category_hub_day">City + Category + Hub + Day</option>
            </select>
          </div>
          {reportData?.available && (
            <div className="card">
              <div className="stat-grid mb-3">
                {Object.entries((reportData.metrics as Record<string, number>) || {}).map(([k, v]) => (
                  <div key={k} className="stat-card">
                    <div className="stat-label">{k}</div>
                    <div className="stat-value">{v != null ? Number(v).toFixed(1) : "—"}</div>
                  </div>
                ))}
              </div>
              <div className="table-wrap" style={{ maxHeight: 400 }}>
                <table>
                  <thead>
                    <tr>
                      {((reportData.columns as string[]) || []).slice(0, 12).map(c => (
                        <th key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {((reportData.rows as Record<string, unknown>[]) || []).slice(0, 50).map((row, i) => (
                      <tr key={i}>
                        {((reportData.columns as string[]) || []).slice(0, 12).map(c => (
                          <td key={c} style={{ fontSize: "0.72rem" }}>{String(row[c] ?? "—")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {report === "city-revenue-trends" && trends && (
        <div>
          <div className="card mb-4">
            <div className="grid-2">
              <FilterChipSelect
                label="Cities"
                options={((trends.filters as { all_cities?: string[] })?.all_cities) || []}
                selected={trendCities}
                onChange={setTrendCities}
                placeholder="Default top cities"
              />
              <FilterChipSelect
                label="Categories"
                options={((trends.filters as { all_categories?: string[] })?.all_categories) || []}
                selected={trendCats}
                onChange={setTrendCats}
                placeholder="All categories"
              />
              <FilterChipSelect
                label="Day of week"
                options={DAY_ORDER}
                selected={trendDays}
                onChange={setTrendDays}
                placeholder="All days"
              />
            </div>
          </div>
          <div className="card mb-4">
            <h4 className="text-sm font-semibold mb-2">Day-on-Day — Last 10 Weeks</h4>
            {(trends.day_on_day as { chart?: unknown })?.chart ? (
              <RevenueTrendChart chart={(trends.day_on_day as { chart: Parameters<typeof RevenueTrendChart>[0]["chart"] }).chart} />
            ) : (
              <p className="text-xs text-muted">No data for selected filters.</p>
            )}
          </div>
          <div className="card">
            <h4 className="text-sm font-semibold mb-2">Week-on-Week — Last 10 Weeks</h4>
            {(trends.week_on_week as { chart?: unknown })?.chart ? (
              <RevenueTrendChart chart={(trends.week_on_week as { chart: Parameters<typeof RevenueTrendChart>[0]["chart"] }).chart} />
            ) : (
              <p className="text-xs text-muted">No data for selected filters.</p>
            )}
          </div>
        </div>
      )}

      {report === "run-history" && (
        <UrlTabs
          param="runhist"
          defaultTab="baseline"
          tabs={[
            {
              id: "baseline",
              label: "Baseline Runs",
              content: (
                <div className="card table-wrap">
                  <table>
                    <thead><tr><th>Run</th><th>Status</th><th>Date</th></tr></thead>
                    <tbody>
                      {baselineRuns.map(r => (
                        <tr key={String(r.run_id)}>
                          <td>{String(r.run_name)}</td>
                          <td>{String(r.status)}</td>
                          <td>{fmt(r.run_date as string)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ),
            },
            {
              id: "final-plan",
              label: "Final Plan Runs",
              content: (
                <div className="card table-wrap">
                  <table>
                    <thead><tr><th>Run</th><th>Status</th><th>Date</th></tr></thead>
                    <tbody>
                      {fpRuns.map(r => (
                        <tr key={String(r.run_id)}>
                          <td>{String(r.run_name)}</td>
                          <td>{String(r.status)}</td>
                          <td>{fmt(r.run_date as string)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ),
            },
          ]}
        />
      )}

      {report === "downloads" && (
        <div className="card">
          <ul className="text-sm">
            {downloads.map((f, i) => (
              <li key={i}>
                <strong>{String(f.type)}</strong>: {String(f.name)} — <code className="text-xs">{String(f.path)}</code>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
