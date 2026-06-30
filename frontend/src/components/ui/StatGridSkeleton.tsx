"use client";

type Props = {
  count?: number;
};

export default function StatGridSkeleton({ count = 4 }: Props) {
  return (
    <div className="stat-grid" aria-hidden>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="stat-card skeleton-stat">
          <div className="skeleton-bar skeleton-label" />
          <div className="skeleton-bar skeleton-value" />
          <div className="skeleton-bar skeleton-hint" />
        </div>
      ))}
    </div>
  );
}
