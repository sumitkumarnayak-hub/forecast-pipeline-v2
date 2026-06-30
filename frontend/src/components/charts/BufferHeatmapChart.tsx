"use client";

import { useMemo, useState, Fragment } from "react";

import { coerceNum } from "@/lib/coerceNum";

type Props = {
  cities: string[];
  categories: string[];
  values: (number | string | null)[][];
};

/** Plotly colorscale: red → white at 0 → green (reporting.py inventory heatmap). */
const COLOR_STOPS: { pos: number; rgb: [number, number, number] }[] = [
  { pos: 0, rgb: [254, 226, 226] },
  { pos: 0.5, rgb: [249, 250, 251] },
  { pos: 1, rgb: [220, 252, 231] },
];

const ZMID = 0;

function flattenValues(values: (number | string | null)[][]): number[] {
  return values
    .flat()
    .map(coerceNum)
    .filter((v): v is number => v != null);
}

/** Match Plotly Heatmap zmid=0 — scale anchored at 0%, not a fixed ±50% clamp. */
function colorPosition(v: number, zmin: number, zmax: number): number {
  if (v <= ZMID) {
    const floor = Math.min(zmin, ZMID);
    const span = ZMID - floor;
    if (span <= 0) return 0.5;
    return 0.5 * (v - floor) / span;
  }
  const ceil = Math.max(zmax, ZMID);
  const span = ceil - ZMID;
  if (span <= 0) return 0.5;
  return 0.5 + 0.5 * (v - ZMID) / span;
}

function interpolateColor(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  for (let i = 0; i < COLOR_STOPS.length - 1; i++) {
    const a = COLOR_STOPS[i];
    const b = COLOR_STOPS[i + 1];
    if (clamped >= a.pos && clamped <= b.pos) {
      const local = b.pos === a.pos ? 0 : (clamped - a.pos) / (b.pos - a.pos);
      const r = Math.round(a.rgb[0] + local * (b.rgb[0] - a.rgb[0]));
      const g = Math.round(a.rgb[1] + local * (b.rgb[1] - a.rgb[1]));
      const bl = Math.round(a.rgb[2] + local * (b.rgb[2] - a.rgb[2]));
      return `rgb(${r}, ${g}, ${bl})`;
    }
  }
  const last = COLOR_STOPS[COLOR_STOPS.length - 1].rgb;
  return `rgb(${last[0]}, ${last[1]}, ${last[2]})`;
}

function bufferColor(v: number | null, zmin: number, zmax: number): string {
  if (v == null || Number.isNaN(v)) return "var(--bg-elevated)";
  return interpolateColor(colorPosition(v, zmin, zmax));
}

function textColor(v: number, zmin: number, zmax: number): string {
  const t = colorPosition(v, zmin, zmax);
  if (t < 0.35 || t > 0.72) return "#1e293b";
  return "#334155";
}

function fmtPct(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 100) return `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`;
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function truncateLabel(s: string, max = 14) {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export default function BufferHeatmapChart({ cities, categories, values }: Props) {
  const [hover, setHover] = useState<{ city: string; cat: string; v: number } | null>(null);

  const { zmin, zmax } = useMemo(() => {
    const flat = flattenValues(values);
    if (!flat.length) return { zmin: -1, zmax: 1 };
    const dataMin = Math.min(...flat);
    const dataMax = Math.max(...flat);
    // Diverging scale always anchored at 0 (matches Plotly zmid=0).
    return {
      zmin: Math.min(dataMin, 0),
      zmax: Math.max(dataMax, 0),
    };
  }, [values]);

  const cellW = useMemo(
    () => Math.max(56, Math.min(80, 900 / Math.max(categories.length, 1))),
    [categories.length],
  );
  const cellH = 32;
  const labelW = 112;

  if (!cities.length || !categories.length) {
    return <div className="chart-empty text-xs text-muted">No inventory buffer data.</div>;
  }

  const gridStyle = {
    display: "grid",
    gridTemplateColumns: `${labelW}px repeat(${categories.length}, ${cellW}px)`,
    gridTemplateRows: `42px repeat(${cities.length}, ${cellH}px)`,
  } as const;

  const legendTop = zmax > 0 ? `+${fmtPct(zmax)}` : fmtPct(zmax);
  const legendBottom = zmin < 0 ? fmtPct(zmin) : zmin > 0 ? "0%" : fmtPct(zmin);

  return (
    <div className="heatmap-shell">
      <div className="heatmap-scroll">
        <div className="heatmap-grid" style={gridStyle}>
          <div className="heatmap-corner" />
          {categories.map(cat => (
            <div key={cat} className="heatmap-col-label" title={cat}>
              {truncateLabel(cat, 16)}
            </div>
          ))}

          {cities.map((city, ri) => (
            <Fragment key={city}>
              <div className="heatmap-row-label" title={city}>
                {city}
              </div>
              {categories.map((cat, ci) => {
                const raw = values[ri]?.[ci] ?? null;
                const v = coerceNum(raw);
                return (
                  <div
                    key={`${city}-${cat}`}
                    className="heatmap-cell"
                    style={{
                      background: bufferColor(v, zmin, zmax),
                      color: v != null ? textColor(v, zmin, zmax) : "var(--text-muted)",
                    }}
                    onMouseEnter={() => v != null && setHover({ city, cat, v })}
                    onMouseLeave={() => setHover(null)}
                    title={v != null ? `${city} · ${cat}: ${fmtPct(v)}` : undefined}
                  >
                    {v != null ? fmtPct(v) : ""}
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>

      <div className="heatmap-side">
        <div className="heatmap-scale-label">Buffer %</div>
        <div className="heatmap-scale-bar" />
        <div className="heatmap-scale-ticks">
          <span title="Max in view">{legendTop}</span>
          <span>0</span>
          <span title="Min in view">{legendBottom}</span>
        </div>
        {hover && (
          <div className="heatmap-hover-card text-xs">
            <div style={{ fontWeight: 700 }}>{hover.city}</div>
            <div className="text-muted">{hover.cat}</div>
            <div
              style={{
                marginTop: "0.35rem",
                fontWeight: 700,
                color: hover.v >= 0 ? "var(--green)" : "var(--red)",
              }}
            >
              {fmtPct(hover.v)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
