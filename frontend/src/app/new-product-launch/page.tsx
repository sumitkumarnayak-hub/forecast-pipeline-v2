"use client";
import { useEffect, useState, useRef } from "react";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import api from "@/lib/api";
import { getUser, canWrite } from "@/lib/auth";
import { Upload, FileSpreadsheet, CheckCircle, XCircle, Table, PlayCircle } from "lucide-react";

export default function NewProductLaunchPage() {
  const user = getUser();
  const [submissions, setSubmissions] = useState<{ rows: any[]; columns: string[] }>({ rows: [], columns: [] });
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/api/new-product-launch/submissions");
      setSubmissions(data);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setMsg({ text: "", type: "" }); setUploadResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/api/new-product-launch/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadResult(data);
      setMsg({ text: `✅ ${file.name} uploaded — ${data.rows} rows validated.`, type: "success" });
      load();
    } catch (err: any) {
      setMsg({ text: `❌ ${err?.response?.data?.detail || "Upload failed"}`, type: "danger" });
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const planTab = (
    <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: "1.25rem" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <FileSpreadsheet size={15} /> Upload NPL Workbook
          </div>
          <div className="text-xs text-muted" style={{ marginBottom: "1rem", lineHeight: 1.6 }}>
            Upload a New Product Launch Excel file. It will be validated using the Pandera schema
            (duplicate detection, required column checks).
          </div>

          {canWrite(user?.role) ? (
            <>
              <label
                style={{
                  display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                  gap: "0.5rem", padding: "1.5rem", borderRadius: "var(--radius-md)",
                  border: "2px dashed var(--border)", cursor: "pointer", background: "var(--bg-elevated)",
                  transition: "border-color 0.15s",
                }}
                onDragOver={e => e.preventDefault()}
              >
                <Upload size={24} color="var(--text-muted)" />
                <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                  {uploading ? "Uploading…" : "Click or drag & drop .xlsx"}
                </span>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".xlsx,.xls"
                  style={{ display: "none" }}
                  onChange={handleUpload}
                  disabled={uploading}
                />
              </label>

              {uploading && (
                <div style={{ textAlign: "center", marginTop: "0.75rem" }}>
                  <span className="spinner" />
                </div>
              )}
            </>
          ) : (
            <div className="alert alert-warning">Viewer role — upload not permitted.</div>
          )}
        </div>
      </div>

      {uploadResult ? (
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: "0.85rem", marginBottom: "0.75rem" }}>Validation Result</div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <span className="badge badge-blue">{uploadResult.rows} rows</span>
            <span className="badge badge-blue">{uploadResult.columns?.length} cols</span>
            {uploadResult.validation?.valid !== undefined && (
              <span className={`badge badge-${uploadResult.validation.valid ? "green" : "red"}`}>
                {uploadResult.validation.valid ? "Valid ✓" : "Invalid ✗"}
              </span>
            )}
          </div>
          {uploadResult.validation?.errors?.length > 0 && (
            <div style={{ marginTop: "0.75rem" }}>
              <div className="text-xs" style={{ color: "var(--red)", fontWeight: 600, marginBottom: "0.25rem" }}>Validation Errors</div>
              {uploadResult.validation.errors.map((e: string, i: number) => (
                <div key={i} style={{ fontSize: "0.72rem", color: "var(--text-secondary)", fontFamily: "monospace", marginBottom: "0.15rem" }}>• {e}</div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
          <div className="text-sm">Upload a workbook to see results</div>
        </div>
      )}
    </div>
  );

  const syncTab = (
    <div className="card">
      <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <Table size={15} /> Launch Submissions (Launch_Output sheet)
      </div>
      {loading ? (
        <div style={{ textAlign: "center", padding: "2rem" }}><span className="spinner" /></div>
      ) : submissions.rows.length === 0 ? (
        <div className="text-xs text-muted">No submissions found in Launch_Output tab.</div>
      ) : (
        <div className="table-wrap" style={{ maxHeight: 480, overflowY: "auto" }}>
          <table>
            <thead>
              <tr>{submissions.columns.map(c => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {submissions.rows.slice(0, 100).map((row, i) => (
                <tr key={i}>
                  {submissions.columns.map(c => (
                    <td key={c} style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>
                      {String(row[c] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  const autoPilotTab = (
    <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
      <PlayCircle size={32} color="var(--text-muted)" style={{ margin: "0 auto 1rem" }} />
      <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.5rem" }}>NPL Auto-Pilot</h3>
      <p className="text-sm text-muted">Automatically process uploaded plan and integrate into baseline pipeline.</p>
    </div>
  );

  const mainTabs = [
    { id: "plan", label: "📝 Plan New Product", content: planTab },
    { id: "sync", label: "🔄 Sync & Write", content: syncTab },
    { id: "auto", label: "⚙️ Auto-Pilot", content: autoPilotTab },
  ];

  return (
    <AppShell
      title="New Product Launch"
      subtitle="Upload and validate new product launch workbooks"
    >
      {msg.text && (
        <div className={`alert alert-${msg.type}`} style={{ marginBottom: "1rem" }}>{msg.text}</div>
      )}

      <Tabs tabs={mainTabs} defaultTab="plan" />
    </AppShell>
  );
}
