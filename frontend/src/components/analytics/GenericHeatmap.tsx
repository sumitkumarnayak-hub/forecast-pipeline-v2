"use client";

import { Fragment, useMemo, useState } from "react";

type Props = {
  rows: string[];
  columns: string[];
  values: (number | null)[][];
  format?: "inr" | "pct" | "number";
};

function fmtInr(v: number) {
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(1)} Cr`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(1)} L`;
  if (a >= 1e3) return `${sign}₹${(a / 1e3).toFixed(1)} K`;
  return `${sign}₹${a.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function fmtCell(v: number | null, format: Props["format"]) {
  if (v == null || Number.isNaN(v)) return "";
  if (format === "pct") return `${v.toFixed(1)}%`;
  if (format === "inr") return fmtInr(v);
  return v >= 1000 ? v.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : v.toFixed(1);
}

function cellColor(v: number | null, format: Props["format"]) {
  if (v == null || Number.isNaN(v)) return "var(--bg-elevated)";
  if (format === "pct") {
    if (v >= 15) return "rgba(239,68,68,0.35)";
    if (v >= 8) return "rgba(245,158,11,0.3)";
    if (v >= 3) return "rgba(250,204,21,0.25)";
    return "rgba(16,185,129,0.15)";
  }
  const max = 1;
  const t = Math.min(1, v / (max || 1));
  const g = Math.round(220 + t * 35);
  return `rgb(237, ${g}, 254)`;
}

export default function GenericHeatmap({ rows, columns, values, format = "number" }: Props) {
  const [hover, setHover] = useState<{ row: string; col: string; v: number } | null>(null);

  const cellW = useMemo(
    () => Math.max(56, Math.min(88, 900 / Math.max(columns.length, 1))),
    [columns.length],
  );
  const cellH = 32;
  const labelW = 120;

  if (!rows.length || !columns.length) {
    return <div className="text-xs text-muted">No heatmap data.</div>;
  }

  const gridStyle = {
    display: "grid",
    gridTemplateColumns: `${labelW}px repeat(${columns.length}, ${cellW}px)`,
    gridTemplateRows: `42px repeat(${rows.length}, ${cellH}px)`,
  } as const;

  return (
    <div className="heatmap-shell">
      <div className="heatmap-scroll">
        <div className="heatmap-grid" style={gridStyle}>
          <div className="heatmap-corner" />
          {columns.map(col => (
            <div key={col} className="heatmap-col-label" title={col}>
              {col.length > 16 ? `${col.slice(0, 15)}…` : col}
            </div>
          ))}
          {rows.map((row, ri) => (
            <Fragment key={row}>
              <div className="heatmap-row-label" title={row}>
                {row.length > 14 ? `${row.slice(0, 13)}…` : row}
              </div>
              {columns.map((col, ci) => {
                const v = values[ri]?.[ci] ?? null;
                const display = v != null && v !== 0 ? fmtCell(v, format) : "";
                return (
                  <div
                    key={`${row}-${col}`}
                    className="heatmap-cell"
                    style={{
                      background: cellColor(v, format),
                      color: "#1e293b",
                      fontSize: "0.65rem",
                    }}
                    onMouseEnter={() => v != null && setHover({ row, col, v })}
                    onMouseLeave={() => setHover(null)}
                    title={v != null ? `${row} · ${col}: ${fmtCell(v, format)}` : undefined}
                  >
                    {display}
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>
      {hover && (
        <div className="heatmap-hover-card text-xs" style={{ marginTop: "0.5rem" }}>
          <div style={{ fontWeight: 700 }}>{hover.row}</div>
          <div className="text-muted">{hover.col}</div>
          <div style={{ marginTop: "0.35rem", fontWeight: 700 }}>{fmtCell(hover.v, format)}</div>
        </div>
      )}
    </div>
  );
}
