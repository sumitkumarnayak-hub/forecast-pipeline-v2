"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import api from "@/lib/api";
import { getUser, isAdmin } from "@/lib/auth";
import { Settings, Bell, Mail, Shield, PlusCircle, Trash2, RefreshCw, Cpu } from "lucide-react";

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

  // General Preferences Content
  const generalTab = (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1.25fr", gap: "1.5rem" }}>
      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 1rem 0", fontSize: "1.05rem", fontWeight: 700 }}>Profile & Role</h4>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          {[
            ["Full Name", user?.full_name],
            ["Email Address", user?.email],
            ["Role Access", user?.role?.toUpperCase()],
          ].map(([label, val]) => (
            <div key={label}>
              <div className="text-xs text-muted mb-1" style={{ fontWeight: 600 }}>{label}</div>
              <div style={{ fontSize: "0.82rem", fontWeight: 500, color: "var(--text-primary)" }}>{val || "—"}</div>
            </div>
          ))}
          <div className="alert alert-info mt-2" style={{ fontSize: "0.72rem" }}>
            Profile updates are managed centrally by the administrator.
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 1rem 0", fontSize: "1.05rem", fontWeight: 700 }}>User Preferences</h4>
        {[
          { key: "email_notifications", label: "Email Notifications", desc: "Receive automated alerts on pipeline checks" },
          { key: "auto_sync_masters",   label: "Auto-Sync Masters",   desc: "Load Google Sheets data on login" },
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
        <div style={{ padding: "1rem 0 0.5rem 0" }}>
          <label className="form-label" style={{ fontWeight: 600 }}>Default Data Preview Rows</label>
          <input
            type="number"
            className="form-input text-sm"
            value={prefs.preview_rows}
            onChange={e => setPrefs(p => ({ ...p, preview_rows: Number(e.target.value) }))}
            min={10} max={1000}
            style={{ width: "100%", maxWidth: "150px" }}
          />
          <div className="text-xs text-muted mt-2">Adjust row limit (10–1000) for preview tables across all tabs.</div>
        </div>
        <button className="btn btn-primary text-sm mt-3" onClick={savePrefs} disabled={saving}>
          {saving ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Saving…</> : "Save Preferences"}
        </button>
      </div>
    </div>
  );

  // Email Notification Recipients Content
  const emailTab = (
    <div style={{ display: "grid", gridTemplateColumns: isAdmin(user?.role) ? "1fr 1.5fr" : "1fr", gap: "1.5rem" }}>
      {isAdmin(user?.role) && (
        <div className="card" style={{ padding: "1.5rem" }}>
          <h4 style={{ margin: "0 0 1rem 0", fontSize: "1.05rem", fontWeight: 700 }}>Add Recipient</h4>
          <div className="form-group">
            <label className="form-label">Email address *</label>
            <input className="form-input text-sm" type="email" placeholder="user@company.com" value={newEmail.email} onChange={e => setNewEmail(n => ({ ...n, email: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Display Name</label>
            <input className="form-input text-sm" placeholder="Optional (e.g. Planning Lead)" value={newEmail.display_name} onChange={e => setNewEmail(n => ({ ...n, display_name: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Alert Category *</label>
            <select className="form-input text-sm" value={newEmail.category} onChange={e => setNewEmail(n => ({ ...n, category: e.target.value }))}>
              <option value="baseline">Baseline Alerts</option>
              <option value="final_plan">Final Plan Submissions</option>
              <option value="pipeline">Pipeline Checks</option>
              <option value="master_sync">Master Data Syncs</option>
            </select>
          </div>
          <button className="btn btn-primary text-sm w-full mt-2" onClick={addRecipient} disabled={addingEmail || !newEmail.email}>
            {addingEmail ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <><PlusCircle size={14} /> Add Recipient</>}
          </button>
        </div>
      )}
      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 1rem 0", fontSize: "1.05rem", fontWeight: 700 }}>Notification Recipients</h4>
        {recipients.length === 0 ? (
          <div className="text-sm text-muted text-center" style={{ padding: "3rem 1rem" }}>
            <Mail size={24} style={{ display: "block", margin: "0 auto 0.75rem", opacity: 0.5 }} />
            No email notification recipients configured.
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Enabled</th>
                  {isAdmin(user?.role) && <th style={{ width: "80px", textAlign: "center" }}>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {recipients.map((r: any) => (
                  <tr key={r.id}>
                    <td style={{ fontSize: "0.78rem", fontWeight: 500 }}>{r.email}</td>
                    <td style={{ fontSize: "0.78rem" }}>{r.display_name || "—"}</td>
                    <td><span className="badge badge-blue">{r.category}</span></td>
                    <td>{r.enabled ? <span className="badge badge-green">Yes</span> : <span className="badge badge-gray">No</span>}</td>
                    {isAdmin(user?.role) && (
                      <td style={{ textAlign: "center" }}>
                        <button className="btn btn-danger btn-sm" style={{ padding: "0.2rem 0.5rem" }} onClick={() => deleteRecipient(r.id)}>
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
  );

  // Environment Config Tab
  const envTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {env && (
        <div className="card" style={{ padding: "1.5rem" }}>
          <h4 style={{ margin: "0 0 1rem 0", fontSize: "1.05rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Cpu size={16} color="var(--indigo)" /> Environment Status
          </h4>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.1rem" }}>
            {[
              { label: "App Environment",   value: env.app_env, badge: env.is_production ? "green" : "yellow" },
              { label: "Database Backend",  value: env.database_backend, badge: env.database_backend === "postgresql" ? "green" : "blue" },
              { label: "SMTP Configured",   value: env.smtp_configured ? "Yes" : "No", badge: env.smtp_configured ? "green" : "red" },
              { label: "Google Credentials", value: env.google_credentials_path ? "Configured" : "Missing", badge: env.google_credentials_path ? "green" : "red" },
              { label: "Pipeline Params Sheet", value: env.pipeline_params_sheet_url ? "Configured" : "Missing", badge: env.pipeline_params_sheet_url ? "green" : "yellow" },
            ].map(row => (
              <div key={row.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.75rem 0", borderBottom: "1px solid var(--border)" }}>
                <div style={{ fontSize: "0.84rem", color: "var(--text-secondary)" }}>{row.label}</div>
                <span className={`badge badge-${row.badge}`}>{row.value}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: "1.25rem", padding: "1rem", background: "var(--bg-hover)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", fontSize: "0.78rem", color: "var(--text-muted)", lineHeight: 1.7 }}>
            <strong style={{ color: "var(--text-primary)", display: "block", marginBottom: "0.3rem" }}>Modify backend parameters:</strong>
            Backend parameters are configured via the server `.env` settings. Please restart the FastAPI server after applying updates.
          </div>
        </div>
      )}
    </div>
  );

  const mainTabs = [
    { id: "general", label: "⚙️ Preferences", content: generalTab },
    { id: "email", label: "📧 Notification Recipients", content: emailTab },
    { id: "env", label: "🛡️ Environment Details", content: envTab },
  ];

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
      {msg.text && <div className={`alert alert-${msg.type}`} style={{ marginBottom: "1.25rem" }}>{msg.text}</div>}

      <Tabs tabs={mainTabs} defaultTab="general" />
    </AppShell>
  );
}
