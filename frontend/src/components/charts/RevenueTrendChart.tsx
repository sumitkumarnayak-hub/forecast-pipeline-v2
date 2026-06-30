"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { coerceNum } from "@/lib/coerceNum";

export type TrendChartPayload = {
  title: string;
  x_label: string;
  x_values?: string[];
  series: {
    group: string;
    color: string;
    points: { x: string; actual: number | null; plan: number | null }[];
  }[];
};

function parseWeekKey(w: string): [number, number] {
  const m = /^(\d{4})-W(\d{1,2})$/.exec(w);
  if (!m) return [0, 0];
  return [Number(m[1]), Number(m[2])];
}

function sortXValues(values: string[], xLabel: string): string[] {
  const unique = [...new Set(values)];
  if (xLabel === "Week") {
    return unique.sort((a, b) => {
      const [ay, aw] = parseWeekKey(a);
      const [by, bw] = parseWeekKey(b);
      return ay !== by ? ay - by : aw - bw;
    });
  }
  if (xLabel === "Date") {
    return unique.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
  }
  return unique.sort();
}

function normalizeX(x: string, xLabel: string): string {
  if (xLabel === "Date" && x.includes("T")) return x.split("T")[0];
  return x;
}

function buildChartRows(chart: TrendChartPayload) {
  const fromSeries = chart.series.flatMap(s => s.points.map(p => p.x));
  const xValues = (chart.x_values?.length
    ? chart.x_values
    : sortXValues(fromSeries, chart.x_label)
  ).map(x => normalizeX(String(x), chart.x_label));

  return xValues.map(x => {
    const row: Record<string, string | number | null> = { x };
    chart.series.forEach((s, i) => {
      const pt = s.points.find(p => normalizeX(String(p.x), chart.x_label) === x);
      row[`a_${i}`] = coerceNum(pt?.actual);
      row[`p_${i}`] = coerceNum(pt?.plan);
    });
    return row;
  });
}

function fmtRupee(v: number) {
  return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function fmtXLabel(x: string, xLabel: string) {
  if (xLabel !== "Date") return x;
  const d = new Date(x);
  if (Number.isNaN(d.getTime())) return x;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

type TooltipProps = {
  active?: boolean;
  payload?: { dataKey?: string; value?: number; color?: string; name?: string }[];
  label?: string;
  chart: TrendChartPayload;
};

function TrendTooltip({ active, payload, label, chart }: TooltipProps) {
  if (!active || !payload?.length || label == null) return null;

  const groups = chart.series.map((s, i) => {
    const actual = coerceNum(payload.find(p => p.dataKey === `a_${i}`)?.value);
    const plan = coerceNum(payload.find(p => p.dataKey === `p_${i}`)?.value);
    if (actual == null && plan == null) return null;
    return { name: s.group, color: s.color, actual, plan };
  }).filter(Boolean) as { name: string; color: string; actual?: number; plan?: number }[];

  if (!groups.length) return null;

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-title">{fmtXLabel(String(label), chart.x_label)}</div>
      {groups.map(g => (
        <div key={g.name} className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: g.color }} />
          <span className="chart-tooltip-name">{g.name}</span>
          <span className="chart-tooltip-values">
            {g.actual != null ? `A ${fmtRupee(g.actual)}` : "A —"}
            {" · "}
            {g.plan != null ? `P ${fmtRupee(g.plan)}` : "P —"}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function RevenueTrendChart({ chart }: { chart: TrendChartPayload }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const check = () => setReady(el.clientWidth > 0);
    check();
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const data = useMemo(() => buildChartRows(chart), [chart]);
  const hasData = data.some(row =>
    chart.series.some((_, i) => row[`a_${i}`] != null || row[`p_${i}`] != null),
  );

  if (!hasData) {
    return (
      <div className="chart-empty text-xs text-muted">
        No chart data for the current filters.
      </div>
    );
  }

  return (
    <div className="chart-panel">
      <div className="chart-panel-header">
        <span className="chart-panel-title">{chart.title}</span>
        <span className="chart-panel-legend-hint">Solid = Actual · Dashed = Plan</span>
      </div>
      <div ref={wrapRef} className="chart-canvas-wrap">
        {!ready ? (
          <div className="chart-skeleton" />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 12, right: 20, left: 4, bottom: 56 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="x"
                tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                tickFormatter={v => fmtXLabel(String(v), chart.x_label)}
                angle={chart.x_label === "Date" ? -35 : 0}
                textAnchor={chart.x_label === "Date" ? "end" : "middle"}
                height={chart.x_label === "Date" ? 64 : 40}
                interval="preserveStartEnd"
                minTickGap={24}
              />
              <YAxis
                width={56}
                tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                tickFormatter={v => `₹${(Number(v) / 100000).toFixed(1)}L`}
              />
              <Tooltip
                content={<TrendTooltip chart={chart} />}
                cursor={{ stroke: "var(--border)", strokeWidth: 1 }}
              />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
              {chart.series.map((s, i) => (
                <Line
                  key={`a-${i}`}
                  type="monotone"
                  dataKey={`a_${i}`}
                  name={s.group}
                  stroke={s.color}
                  strokeWidth={2}
                  dot={{ r: 2.5, fill: s.color, strokeWidth: 0 }}
                  activeDot={{ r: 4 }}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
              {chart.series.map((s, i) => (
                <Line
                  key={`p-${i}`}
                  type="monotone"
                  dataKey={`p_${i}`}
                  name={`${s.group} · Plan`}
                  stroke={s.color}
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                  legendType="none"
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
