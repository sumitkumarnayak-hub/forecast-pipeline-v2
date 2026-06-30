import type { ReactNode } from "react";

interface Props {
  title: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
}

export default function SectionCard({ title, description, children, actions }: Props) {
  return (
    <div className="card" style={{ marginBottom: "1.25rem" }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "0.75rem",
          marginBottom: description ? "0.5rem" : "0.75rem",
        }}
      >
        <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{title}</div>
        {actions}
      </div>
      {description && (
        <p className="text-xs text-muted" style={{ marginBottom: "1rem", lineHeight: 1.6 }}>
          {description}
        </p>
      )}
      {children}
    </div>
  );
}
