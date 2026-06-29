"use client";
import { useRef, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import api from "@/lib/api";
import { getUser, canWrite } from "@/lib/auth";
import { Upload, CheckCircle, XCircle, ShieldCheck, FileCode2 } from "lucide-react";

export default function ValidationPage() {
  const user = getUser();
  const fileRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<any>(null);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setMsg({ text: "", type: "" }); setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/api/validation/validate-baseline-output", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data);
      const valid = data.validation?.valid !== false;
      setMsg({ text: `${valid ? "✅" : "❌"} ${file.name} — ${data.rows} rows, ${valid ? "validation passed" : "validation failed"}`, type: valid ? "success" : "danger" });
    } catch (err: any) {
      setMsg({ text: `❌ ${err?.response?.data?.detail || "Validation failed"}`, type: "danger" });
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const validateOutputsTab = (
    <div className="grid-2">
      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <ShieldCheck size={15} color="var(--blue)" /> Validate Baseline Output
          </div>
          <div className="text-xs text-muted" style={{ marginBottom: "1rem", lineHeight: 1.6 }}>
            Upload a <code style={{ background: "rgba(255,255,255,0.08)", padding: "0 3px", borderRadius: 3 }}>Summary_*.xlsx</code> file.
            It will be validated against the Pandera baseline schema — required columns, null checks, and data constraints.
          </div>

          {canWrite(user?.role) ? (
            <label style={{
              display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
              gap: "0.5rem", padding: "2rem", borderRadius: "var(--radius-md)",
              border: "2px dashed var(--border)", cursor: "pointer", background: "var(--bg-elevated)",
              transition: "border-color 0.15s",
            }}>
              <Upload size={28} color="var(--text-muted)" />
              <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                {uploading ? "Validating…" : "Click to upload Summary_*.xlsx"}
              </span>
              <span className="text-xs text-muted">Pandera schema validation</span>
              <input ref={fileRef} type="file" accept=".xlsx,.xls" style={{ display: "none" }} onChange={handleUpload} disabled={uploading} />
            </label>
          ) : (
            <div className="alert alert-warning">Viewer role — upload not permitted.</div>
          )}

          {uploading && <div style={{ textAlign: "center", marginTop: "0.75rem" }}><span className="spinner" /></div>}
        </div>

        <div className="card" style={{ background: "var(--blue-dim)", borderColor: "var(--border-accent)" }}>
          <div style={{ fontWeight: 700, fontSize: "0.85rem", marginBottom: "0.5rem", color: "var(--blue)" }}>📋 Schema Checks</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", lineHeight: 1.8 }}>
            The Pandera schema validates:<br />
            • Required columns present<br />
            • No null values in key fields<br />
            • Numeric columns are non-negative<br />
            • Date columns are valid<br />
            • Hub/SKU codes match expected patterns
          </div>
        </div>
      </div>

      <div className="card">
        <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>Validation Result</div>

        {msg.text && (
          <div className={`alert alert-${msg.type}`} style={{ marginBottom: "1rem" }}>{msg.text}</div>
        )}

        {!result ? (
          <div style={{ textAlign: "center", padding: "4rem 2rem", color: "var(--text-muted)" }}>
            <ShieldCheck size={48} style={{ opacity: 0.2, marginBottom: "1rem" }} />
            <div style={{ fontSize: "0.85rem" }}>Upload a baseline output file to see validation results here.</div>
          </div>
        ) : (
          <>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1.25rem" }}>
              <span className="badge badge-blue">{result.rows} rows</span>
              <span className="badge badge-blue">{result.columns?.length} columns</span>
              <span className={`badge badge-${result.validation?.valid !== false ? "green" : "red"}`}>
                {result.validation?.valid !== false ? <><CheckCircle size={11} /> Passed</> : <><XCircle size={11} /> Failed</>}
              </span>
            </div>

            {result.validation?.errors?.length > 0 && (
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.78rem", color: "var(--red)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.6rem" }}>
                  Validation Errors ({result.validation.errors.length})
                </div>
                <div style={{ maxHeight: 320, overflowY: "auto" }}>
                  {result.validation.errors.map((e: string, i: number) => (
                    <div key={i} style={{
                      display: "flex", gap: "0.5rem", alignItems: "flex-start",
                      padding: "0.5rem 0.75rem", background: "var(--red-dim)",
                      borderRadius: "var(--radius-sm)", marginBottom: "0.35rem",
                      fontSize: "0.75rem", color: "#fca5a5", fontFamily: "monospace",
                    }}>
                      <XCircle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
                      {e}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {result.validation?.valid !== false && (
              <div style={{ marginTop: "1rem" }}>
                <div style={{ fontWeight: 600, fontSize: "0.78rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.5rem" }}>
                  Validated Columns
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
                  {(result.columns || []).map((c: string) => (
                    <span key={c} style={{ fontSize: "0.68rem", background: "var(--green-dim)", border: "1px solid rgba(16,185,129,0.2)", padding: "0.15rem 0.5rem", borderRadius: 4, color: "var(--green)", fontFamily: "monospace" }}>
                      ✓ {c}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );

  const logicsTab = (
    <div className="card" style={{ textAlign: "center", padding: "4rem 2rem", color: "var(--text-muted)" }}>
      <FileCode2 size={48} style={{ opacity: 0.2, margin: "0 auto 1rem" }} />
      <div style={{ fontSize: "0.9rem", fontWeight: 600, marginBottom: "0.5rem" }}>Logics Used</div>
      <div className="text-sm">Documentation for the validation logic rules applied during checking.</div>
    </div>
  );

  const mainTabs = [
    { id: "validate", label: "📊 Validate Outputs", content: validateOutputsTab },
    { id: "logics", label: "📝 Logics Used", content: logicsTab },
  ];

  return (
    <AppShell
      title="Output Validation"
      subtitle="Validate baseline summary Excel outputs using Pandera schemas"
    >
      <Tabs tabs={mainTabs} defaultTab="validate" />
    </AppShell>
  );
}
