"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import api from "@/lib/api";
import { getUser, isAdmin } from "@/lib/auth";
import { Settings, Bell, Mail, Shield, PlusCircle, Trash2, RefreshCw } from "lucide-react";

type Pref = { email_notifications: boolean; auto_sync_masters: boolean; preview_rows: number };

export default function SettingsPage() {
  const user = getUser();
  const [env, setEnv] = useState<any>(null);
  const [prefs, setPrefs] = useState<Pref>({ email_notifications: true, auto_sync_masters: false, preview_rows: 100 });
  const [recipients, setRecipients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });
  const [newEmail, setNewEmail] = useState({ email: "", display_name: "", category: "baseline" });
  const [addingEmail, setAddingEmail] = useState(false);
  const [tab, setTab] = useState<"general" | "email" | "env">("general");

  const load = async () => {
    setLoading(true);
    try {
      const [e, p] = await Promise.all([
        api.get("/api/settings/env-status"),
        api.get("/api/settings/preferences"),
      ]);
      setEnv(e.data);
      if (p.data && Object.keys(p.data).length > 0) setPrefs({ ...prefs, ...p.data });
      if (isAdmin(user?.role)) {
        const r = await api.get("/api/settings/email-recipients");
        setRecipients(r.data);
      }
    } catch {}
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const savePrefs = async () => {
    setSaving(true); setMsg({ text: "", type: "" });
    try {
      await api.post("/api/settings/preferences", prefs);
      setMsg({ text: "✅ Preferences saved.", type: "success" });
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Save failed"}`, type: "danger" });
    }
    setSaving(false);
  };

  const addRecipient = async () => {
    if (!newEmail.email) return;
    setAddingEmail(true);
    try {
      await api.post("/api/settings/email-recipients", newEmail);
      setMsg({ text: `✅ ${newEmail.email} added.`, type: "success" });
      setNewEmail({ email: "", display_name: "", category: "baseline" });
      load();
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Failed"}`, type: "danger" });
    }
    setAddingEmail(false);
  };

  const deleteRecipient = async (id: number) => {
    try {
      await api.delete(`/api/settings/email-recipients/${id}`);
      setRecipients(r => r.filter(x => x.id !== id));
      setMsg({ text: "✅ Recipient removed.", type: "success" });
    } catch (e: any) {
      setMsg({ text: `❌ ${e?.response?.data?.detail || "Failed"}`, type: "danger" });
    }
  };

  const TABS = [
    { key: "general", label: "General",    icon: <Settings size={13} /> },
    { key: "email",   label: "Email",      icon: <Mail size={13} /> },
    { key: "env",     label: "Environment", icon: <Shield size={13} /> },
  ] as const;

  return (
    <AppShell
      title="Settings"
      subtitle="Preferences, email recipients & environment status"
      actions={
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {msg.text && <div className={`alert alert-${msg.type}`} style={{ marginBottom: "1rem" }}>{msg.text}</div>}

      {/* Tabs */}
      <div style={{ display: "flex", gap: "0.25rem", borderBottom: "1px solid var(--border)", marginBottom: "1.25rem" }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key as any)}
            style={{
              padding: "0.5rem 1rem", border: "none", background: "none", cursor: "pointer",
              fontSize: "0.82rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.4rem",
              color: tab === t.key ? "var(--blue)" : "var(--text-muted)",
              borderBottom: tab === t.key ? "2px solid var(--blue)" : "2px solid transparent",
              marginBottom: -1, transition: "color 0.15s",
            }}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* General preferences */}
      {tab === "general" && (
        <div className="card" style={{ maxWidth: 500 }}>
          <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "1rem" }}>User Preferences</div>
          {[
            { key: "email_notifications", label: "Email Notifications", desc: "Receive success/failure emails for pipeline runs" },
            { key: "auto_sync_masters",   label: "Auto-Sync Masters",   desc: "Automatically sync masters on login" },
          ].map(opt => (
            <div key={opt.key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.75rem 0", borderBottom: "1px solid var(--border)" }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.84rem" }}>{opt.label}</div>
                <div className="text-xs text-muted">{opt.desc}</div>
              </div>
              <label style={{ position: "relative", display: "inline-flex", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={(prefs as any)[opt.key]}
                  onChange={e => setPrefs(p => ({ ...p, [opt.key]: e.target.checked }))}
                  style={{ display: "none" }}
                />
                <div style={{
                  width: 36, height: 20, borderRadius: 10, transition: "0.2s",
                  background: (prefs as any)[opt.key] ? "var(--blue)" : "var(--bg-hover)",
                  border: "1px solid var(--border)", position: "relative",
                }}>
                  <div style={{
                    width: 14, height: 14, borderRadius: "50%", background: "#fff",
                    position: "absolute", top: 2,
                    left: (prefs as any)[opt.key] ? 18 : 2,
                    transition: "left 0.2s",
                  }} />
                </div>
              </label>
            </div>
          ))}
          <div style={{ padding: "0.75rem 0" }}>
            <label className="form-label">Preview Rows</label>
            <input
              type="number"
              className="form-input"
              value={prefs.preview_rows}
              onChange={e => setPrefs(p => ({ ...p, preview_rows: Number(e.target.value) }))}
              min={10} max={1000}
              style={{ width: 120 }}
            />
            <div className="text-xs text-muted" style={{ marginTop: "0.25rem" }}>Number of rows to preview in data tables (10–1000)</div>
          </div>
          <button className="btn btn-primary" onClick={savePrefs} disabled={saving} style={{ marginTop: "0.75rem" }}>
            {saving ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Saving…</> : "Save Preferences"}
          </button>
        </div>
      )}

      {/* Email recipients */}
      {tab === "email" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1.5fr", gap: "1.25rem" }}>
          {isAdmin(user?.role) && (
            <div className="card">
              <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>Add Recipient</div>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input className="form-input" type="email" placeholder="user@example.com" value={newEmail.email} onChange={e => setNewEmail(n => ({ ...n, email: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Display Name</label>
                <input className="form-input" placeholder="Optional" value={newEmail.display_name} onChange={e => setNewEmail(n => ({ ...n, display_name: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Category</label>
                <select className="form-input" value={newEmail.category} onChange={e => setNewEmail(n => ({ ...n, category: e.target.value }))}>
                  <option value="baseline">Baseline</option>
                  <option value="final_plan">Final Plan</option>
                  <option value="pipeline">Pipeline</option>
                  <option value="master_sync">Master Sync</option>
                </select>
              </div>
              <button className="btn btn-primary w-full" onClick={addRecipient} disabled={addingEmail || !newEmail.email}>
                {addingEmail ? <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> : <PlusCircle size={13} />} Add Recipient
              </button>
            </div>
          )}
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.75rem" }}>Email Recipients</div>
            {recipients.length === 0 ? <div className="text-xs text-muted">No email recipients configured.</div> : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Email</th><th>Name</th><th>Category</th><th>Enabled</th>{isAdmin(user?.role) && <th></th>}</tr></thead>
                  <tbody>
                    {recipients.map((r: any) => (
                      <tr key={r.id}>
                        <td style={{ fontSize: "0.75rem" }}>{r.email}</td>
                        <td style={{ fontSize: "0.75rem" }}>{r.display_name || "—"}</td>
                        <td><span className="badge badge-blue">{r.category}</span></td>
                        <td>{r.enabled ? <span className="badge badge-green">Yes</span> : <span className="badge badge-gray">No</span>}</td>
                        {isAdmin(user?.role) && (
                          <td>
                            <button className="btn btn-danger btn-sm" onClick={() => deleteRecipient(r.id)}>
                              <Trash2 size={11} />
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Environment status */}
      {tab === "env" && env && (
        <div className="card" style={{ maxWidth: 600 }}>
          <div style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "1rem" }}>Environment Status</div>
          {[
            { label: "App Environment",   value: env.app_env, badge: env.is_production ? "green" : "yellow" },
            { label: "Database Backend",  value: env.database_backend, badge: env.database_backend === "postgresql" ? "green" : "blue" },
            { label: "SMTP Configured",   value: env.smtp_configured ? "Yes" : "No", badge: env.smtp_configured ? "green" : "red" },
            { label: "Google Credentials", value: env.google_credentials_path ? "Configured" : "Missing", badge: env.google_credentials_path ? "green" : "red" },
            { label: "Pipeline Params Sheet", value: env.pipeline_params_sheet_url ? "Configured" : "Missing", badge: env.pipeline_params_sheet_url ? "green" : "yellow" },
          ].map(row => (
            <div key={row.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.65rem 0", borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontSize: "0.84rem", color: "var(--text-secondary)" }}>{row.label}</div>
              <span className={`badge badge-${row.badge}`}>{row.value}</span>
            </div>
          ))}
          <div style={{ marginTop: "0.75rem", padding: "0.75rem", background: "var(--bg-elevated)", borderRadius: "var(--radius-md)", fontSize: "0.72rem", color: "var(--text-muted)", lineHeight: 1.7 }}>
            <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>Modify configuration</div>
            Edit <code style={{ background: "rgba(255,255,255,0.08)", padding: "0 4px", borderRadius: 3 }}>backend/.env</code> and restart the backend server to apply changes.
          </div>
        </div>
      )}
    </AppShell>
  );
}
