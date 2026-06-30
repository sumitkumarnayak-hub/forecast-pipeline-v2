"use client";

import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

type DailyPoint = { date: string; [key: string]: string | number | null };

export function DualLineChart({
  data,
  xKey,
  lines,
  height = 280,
}: {
  data: DailyPoint[];
  xKey: string;
  lines: { key: string; name: string; color: string; dashed?: boolean }[];
  height?: number;
}) {
  if (!data.length) return <div className="text-xs text-muted">No trend data.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
        <YAxis tick={{ fontSize: 10 }} tickFormatter={v => `₹${Number(v).toLocaleString("en-IN", { notation: "compact" })}`} />
        <Tooltip formatter={(v: number) => `₹${v.toLocaleString("en-IN")}`} />
        <Legend />
        {lines.map(l => (
          <Line
            key={l.key}
            type="monotone"
            dataKey={l.key}
            name={l.name}
            stroke={l.color}
            strokeWidth={2}
            strokeDasharray={l.dashed ? "5 5" : undefined}
            dot={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function StackedLossChart({
  data,
  height = 320,
}: {
  data: { label: string; demand: number; supply: number }[];
  height?: number;
}) {
  if (!data.length) return <div className="text-xs text-muted">No loss data.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="label" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10 }} tickFormatter={v => `₹${Number(v).toLocaleString("en-IN", { notation: "compact" })}`} />
        <Tooltip formatter={(v: number) => `₹${v.toLocaleString("en-IN")}`} />
        <Legend />
        <Bar dataKey="demand" name="Demand-led" stackId="a" fill="#EF4444" />
        <Bar dataKey="supply" name="Supply-led" stackId="a" fill="#F59E0B" />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SimpleBarChart({
  data,
  xKey,
  yKey,
  color = "#6366F1",
  horizontal = false,
  height = 360,
}: {
  data: Record<string, unknown>[];
  xKey: string;
  yKey: string;
  color?: string;
  horizontal?: boolean;
  height?: number;
}) {
  if (!data.length) return <div className="text-xs text-muted">No data.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        {horizontal ? (
          <>
            <XAxis type="number" tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey={xKey} width={140} tick={{ fontSize: 9 }} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} tick={{ fontSize: 9 }} />
            <YAxis tick={{ fontSize: 10 }} />
          </>
        )}
        <Tooltip />
        <Bar dataKey={yKey} fill={color} />
      </BarChart>
    </ResponsiveContainer>
  );
}
