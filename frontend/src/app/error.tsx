"use client";

import Link from "next/link";
import { AlertCircle, RefreshCw, Home } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "Inter, system-ui, sans-serif", background: "#f8fafc" }}>
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "2rem",
          }}
        >
          <div
            className="card"
            style={{
              maxWidth: 440,
              width: "100%",
              padding: "2rem",
              textAlign: "center",
              border: "1px solid #e2e8f0",
              borderRadius: 14,
              background: "#fff",
            }}
          >
            <AlertCircle size={40} color="#dc2626" style={{ margin: "0 auto 1rem" }} />
            <h1 style={{ fontSize: "1.25rem", margin: "0 0 0.5rem" }}>Something went wrong</h1>
            <p style={{ color: "#64748b", fontSize: "0.9rem", lineHeight: 1.6, margin: "0 0 1.5rem" }}>
              An unexpected error occurred. Try refreshing the page. If the problem continues, contact your administrator.
            </p>
            {error.digest && (
              <p style={{ fontSize: "0.72rem", color: "#94a3b8", marginBottom: "1rem" }}>
                Reference: {error.digest}
              </p>
            )}
            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "center", flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={() => reset()}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "0.5rem 1rem",
                  borderRadius: 8,
                  border: "none",
                  background: "#2563eb",
                  color: "#fff",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                }}
              >
                <RefreshCw size={14} /> Try again
              </button>
              <Link
                href="/dashboard"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "0.5rem 1rem",
                  borderRadius: 8,
                  border: "1px solid #e2e8f0",
                  background: "#fff",
                  color: "#0f172a",
                  textDecoration: "none",
                  fontSize: "0.85rem",
                }}
              >
                <Home size={14} /> Dashboard
              </Link>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
