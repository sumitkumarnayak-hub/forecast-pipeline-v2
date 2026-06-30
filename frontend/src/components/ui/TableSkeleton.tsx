"use client";

type Props = {
  rows?: number;
  cols?: number;
  className?: string;
};

export default function TableSkeleton({ rows = 6, cols = 5, className = "" }: Props) {
  return (
    <div className={`table-skeleton ${className}`.trim()} aria-hidden>
      <div className="table-skeleton-head">
        {Array.from({ length: cols }).map((_, i) => (
          <div key={i} className="skeleton-bar skeleton-th" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="table-skeleton-row">
          {Array.from({ length: cols }).map((_, c) => (
            <div
              key={c}
              className="skeleton-bar"
              style={{ width: c === 0 ? "72%" : c === cols - 1 ? "45%" : "88%" }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
