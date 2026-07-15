"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { Tabs } from "@/components/ui/Tabs";
import api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  User,
  Users,
  Settings,
  Mail,
  Monitor,
  Info,
  BookOpen,
  PlusCircle,
  Trash2,
  RefreshCw,
  Pencil,
  Send,
  Save,
} from "lucide-react";
import { readSessionBootstrap, writeSessionBootstrap, BOOTSTRAP_TTL_MS } from "@/lib/bootstrapCache";
import UsersAdminTab from "@/components/settings/UsersAdminTab";

const DEFAULT_RECIPIENT_CATEGORIES: Record<string, string> = {
  all: "All notifications",
  approval: "Approval required (baseline)",
  launch_planner: "New launch — planners",
  launch_admin: "New launch — admin approval",
  pipeline: "Pipeline & run failures",
  validation: "Validation results",
  general: "General notifications",
};

const BOOTSTRAP_KEY = "settings:bootstrap";

type Pref = { email_notifications: boolean; auto_sync_masters: boolean; preview_rows: number };

type Bootstrap = {
  profile?: { id?: number; full_name?: string; email?: string; role?: string };
  preferences?: Pref;
  env?: Record<string, unknown>;
  recipient_categories?: Record<string, string>;
  recipients?: Recipient[];
  email_log?: EmailLogRow[];
  session?: SessionInfo;
  about?: Record<string, string>;
};

type Recipient = {
  id: number;
  email: string;
  display_name?: string;
  category: string;
  enabled: boolean | number;
};

type EmailLogRow = {
  id?: number;
  sent_at?: string;
  email_type?: string;
  subject?: string;
  recipients?: string;
  status?: string;
  error_message?: string;
  triggered_by?: string;
};

type SessionInfo = {
  has_session?: boolean;
  session_id?: string | null;
  session_created_at?: string | null;
  session_expires_at?: string | null;
  stored_system_details?: Record<string, unknown> | null;
  live_server_details?: Record<string, string>;
  token_expires_at?: string | null;
};

function collectClientInfo(): Record<string, string> {
  if (typeof window === "undefined") return {};
  return {
    browser_user_agent: navigator.userAgent || "",
    browser_platform: navigator.platform || "",
    browser_language: navigator.language || "",
    screen_resolution: window.screen ? `${window.screen.width}x${window.screen.height}` : "",
    client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
    client_timestamp: new Date().toISOString(),
  };
}

function fmtJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

export default function SettingsPage() {
  const { user, hydrated } = useAuth();
  const admin = hydrated && user?.role === "admin";

  const [boot, setBoot] = useState<Bootstrap | null>(() => readSessionBootstrap(BOOTSTRAP_KEY, BOOTSTRAP_TTL_MS));
  const [prefs, setPrefs] = useState<Pref>(() => {
    const cached = readSessionBootstrap<Bootstrap>(BOOTSTRAP_KEY, BOOTSTRAP_TTL_MS);
    return cached?.preferences ?? { email_notifications: true, auto_sync_masters: false, preview_rows: 100 };
  });
  const [loading, setLoading] = useState(() => !readSessionBootstrap(BOOTSTRAP_KEY, BOOTSTRAP_TTL_MS));
  const [saving, setSaving] = useState(false);
  const [addingEmail, setAddingEmail] = useState(false);
  const [msg, setMsg] = useState({ text: "", type: "" });

  const [newEmail, setNewEmail] = useState({ email: "", display_name: "", category: "general" });
  const [editId, setEditId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ email: "", display_name: "", category: "general", enabled: true });

  const [testRecipientId, setTestRecipientId] = useState<number | "">("");
  const [testMsg, setTestMsg] = useState("");
  const [sendingTest, setSendingTest] = useState(false);

  const [clientInfo, setClientInfo] = useState<Record<string, string>>({});
  const [savingSession, setSavingSession] = useState(false);

  const loadBootstrap = useCallback(async (force?: boolean) => {
    const cached = !force ? readSessionBootstrap<Bootstrap>(BOOTSTRAP_KEY, BOOTSTRAP_TTL_MS) : null;
    if (cached) {
      setBoot(cached);
      if (cached.preferences) setPrefs(cached.preferences);
      setLoading(false);
      return;
    }
    setLoading(true);
    setMsg({ text: "", type: "" });
    try {
      const { data } = await api.get<Bootstrap>("/api/settings/bootstrap");
      setBoot(data);
      if (data.preferences) setPrefs(data.preferences);
      writeSessionBootstrap(BOOTSTRAP_KEY, data);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      if (!cached) {
        setMsg({ text: err?.response?.data?.detail || "Failed to load settings", type: "danger" });
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    setClientInfo(collectClientInfo());
    
    // Read from cache first. If cache is valid and belongs to the current user,
    // load it instantly to avoid showing the loading spinner, then refresh in background.
    const cached = readSessionBootstrap<Bootstrap>(BOOTSTRAP_KEY, BOOTSTRAP_TTL_MS);
    if (cached && cached.profile?.id === user?.id) {
      setBoot(cached);
      if (cached.preferences) setPrefs(cached.preferences);
      setLoading(false);
      // Fetch in the background to update cache without showing a loading spinner
      api.get<Bootstrap>("/api/settings/bootstrap")
        .then(({ data }) => {
          setBoot(data);
          if (data.preferences) setPrefs(data.preferences);
          writeSessionBootstrap(BOOTSTRAP_KEY, data);
        })
        .catch(() => {});
    } else {
      setBoot(null);
      setPrefs({ email_notifications: true, auto_sync_masters: false, preview_rows: 100 });
      void loadBootstrap(true);
    }
  }, [hydrated, user?.id, loadBootstrap]);

  const savePrefs = async () => {
    setSaving(true);
    setMsg({ text: "", type: "" });
    try {
      await api.post("/api/settings/preferences", prefs);
      setMsg({ text: "Preferences saved.", type: "success" });
      sessionStorage.removeItem(BOOTSTRAP_KEY);
      await loadBootstrap(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Save failed", type: "danger" });
    }
    setSaving(false);
  };

  const addRecipient = async () => {
    if (!newEmail.email) return;
    setAddingEmail(true);
    try {
      await api.post("/api/settings/email-recipients", newEmail);
      setMsg({ text: `${newEmail.email} added.`, type: "success" });
      setNewEmail({ email: "", display_name: "", category: "general" });
      sessionStorage.removeItem(BOOTSTRAP_KEY);
      await loadBootstrap(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Failed", type: "danger" });
    }
    setAddingEmail(false);
  };

  const startEdit = (r: Recipient) => {
    setEditId(r.id);
    setEditForm({
      email: r.email,
      display_name: r.display_name || "",
      category: r.category,
      enabled: Boolean(r.enabled),
    });
  };

  const saveEdit = async () => {
    if (editId == null) return;
    try {
      await api.patch(`/api/settings/email-recipients/${editId}`, editForm);
      setMsg({ text: "Recipient updated.", type: "success" });
      setEditId(null);
      sessionStorage.removeItem(BOOTSTRAP_KEY);
      await loadBootstrap(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Update failed", type: "danger" });
    }
  };

  const deleteRecipient = async (id: number) => {
    try {
      await api.delete(`/api/settings/email-recipients/${id}`);
      setMsg({ text: "Recipient removed.", type: "success" });
      sessionStorage.removeItem(BOOTSTRAP_KEY);
      await loadBootstrap(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Failed", type: "danger" });
    }
  };

  const sendTestEmail = async () => {
    setSendingTest(true);
    try {
      const body: { recipient_id?: number; message: string } = { message: testMsg };
      if (testRecipientId !== "") body.recipient_id = Number(testRecipientId);
      await api.post("/api/settings/test-email", body);
      setMsg({ text: "Test email sent.", type: "success" });
      sessionStorage.removeItem(BOOTSTRAP_KEY);
      await loadBootstrap(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Send failed", type: "danger" });
    }
    setSendingTest(false);
  };

  const saveSessionDetails = async () => {
    setSavingSession(true);
    try {
      const info = collectClientInfo();
      setClientInfo(info);
      await api.post("/api/settings/session/system-details", { client_info: info });
      setMsg({ text: "System details saved to session.", type: "success" });
      sessionStorage.removeItem(BOOTSTRAP_KEY);
      await loadBootstrap(true);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMsg({ text: err?.response?.data?.detail || "Save failed", type: "danger" });
    }
    setSavingSession(false);
  };

  const profile = boot?.profile || user;
  const env = boot?.env;
  const recipients = boot?.recipients || [];
  const categories = boot?.recipient_categories || DEFAULT_RECIPIENT_CATEGORIES;
  const session = boot?.session;
  const emailLog = boot?.email_log || [];

  const profileTab = (
    <div className="card" style={{ padding: "1.5rem", maxWidth: 520 }}>
      <h4 style={{ margin: "0 0 1rem", fontSize: "1.05rem", fontWeight: 700 }}>Your Profile</h4>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        {[
          ["Full Name", profile?.full_name],
          ["Email Address", profile?.email],
          ["Role", profile?.role?.toUpperCase()],
        ].map(([label, val]) => (
          <div key={String(label)}>
            <div className="text-xs text-muted mb-1" style={{ fontWeight: 600 }}>{label}</div>
            <div style={{ fontSize: "0.82rem", fontWeight: 500 }}>{val || "—"}</div>
          </div>
        ))}
      </div>
      <div className="alert alert-info mt-3" style={{ fontSize: "0.72rem" }}>
        Profile updates are managed centrally by your administrator.
      </div>
    </div>
  );

  const preferencesTab = (
    <div className="card" style={{ padding: "1.5rem", maxWidth: 640 }}>
      <h4 style={{ margin: "0 0 1rem", fontSize: "1.05rem", fontWeight: 700 }}>User Preferences</h4>
      {[
        { key: "email_notifications", label: "Email Notifications", desc: "Receive automated alerts on pipeline checks" },
        { key: "auto_sync_masters", label: "Auto-Sync Masters", desc: "Load Google Sheets data on login" },
      ].map(opt => {
        const key = opt.key as "email_notifications" | "auto_sync_masters";
        return (
        <div
          key={opt.key}
          style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "0.75rem 0", borderBottom: "1px solid var(--border)",
          }}
        >
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.84rem" }}>{opt.label}</div>
            <div className="text-xs text-muted">{opt.desc}</div>
          </div>
          <label style={{ position: "relative", display: "inline-flex", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={prefs[key]}
              onChange={e => setPrefs(p => ({ ...p, [key]: e.target.checked }))}
              style={{ display: "none" }}
            />
            <div
              style={{
                width: 36, height: 20, borderRadius: 10, transition: "0.2s",
                background: prefs[key] ? "var(--blue)" : "var(--bg-hover)",
                border: "1px solid var(--border)", position: "relative",
              }}
            >
              <div
                style={{
                  width: 14, height: 14, borderRadius: "50%", background: "#fff",
                  position: "absolute", top: 2,
                  left: prefs[key] ? 18 : 2,
                  transition: "left 0.2s",
                }}
              />
            </div>
          </label>
        </div>
        );
      })}
      <div style={{ padding: "1rem 0 0.5rem" }}>
        <label className="form-label" style={{ fontWeight: 600 }}>Default Data Preview Rows</label>
        <input
          type="number"
          className="form-input text-sm"
          value={prefs.preview_rows}
          onChange={e => setPrefs(p => ({ ...p, preview_rows: Number(e.target.value) }))}
          min={10}
          max={1000}
          style={{ width: "100%", maxWidth: 150 }}
        />
        <div className="text-xs text-muted mt-2">Row limit (10–1000) for preview tables across the app.</div>
      </div>
      <button className="btn btn-primary text-sm mt-3" onClick={savePrefs} disabled={saving}>
        {saving ? "Saving…" : "Save Preferences"}
      </button>
    </div>
  );

  const emailTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {env && (
        <div className="card" style={{ padding: "1rem 1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span className="text-sm">SMTP status</span>
            <span className={`badge badge-${env.smtp_configured ? "green" : "red"}`}>
              {env.smtp_configured ? "Configured" : "Not configured"}
            </span>
          </div>
        </div>
      )}

      {admin && (
        <div className="layout-split">
          <div className="card" style={{ padding: "1.5rem" }}>
            <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>Send Test Email</h4>
            <div className="form-group">
              <label className="form-label">Recipient</label>
              <select
                className="form-input text-sm"
                value={testRecipientId}
                onChange={e => setTestRecipientId(e.target.value === "" ? "" : Number(e.target.value))}
              >
                <option value="">Your profile email (fallback)</option>
                {recipients.filter(r => r.enabled).map(r => (
                  <option key={r.id} value={r.id}>{r.display_name || r.email} ({r.email})</option>
                ))}
              </select>
            </div>
            <textarea
              className="form-input text-sm mb-2"
              rows={2}
              placeholder="Optional message"
              value={testMsg}
              onChange={e => setTestMsg(e.target.value)}
            />
            <button className="btn btn-primary btn-sm w-full" onClick={sendTestEmail} disabled={sendingTest}>
              {sendingTest ? "Sending…" : <><Send size={14} /> Send test email</>}
            </button>
          </div>

          <div className="card" style={{ padding: "1.5rem" }}>
            <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>Add Recipient</h4>
            <div className="form-group">
              <label className="form-label">Email *</label>
              <input
                className="form-input text-sm"
                type="email"
                value={newEmail.email}
                onChange={e => setNewEmail(n => ({ ...n, email: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Display name</label>
              <input
                className="form-input text-sm"
                value={newEmail.display_name}
                onChange={e => setNewEmail(n => ({ ...n, display_name: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Category *</label>
              <select
                className="form-input text-sm"
                value={newEmail.category}
                onChange={e => setNewEmail(n => ({ ...n, category: e.target.value }))}
              >
                {Object.entries(categories).map(([id, label]) => (
                  <option key={id} value={id}>{label}</option>
                ))}
              </select>
            </div>
            <button
              className="btn btn-primary text-sm w-full"
              onClick={addRecipient}
              disabled={addingEmail || !newEmail.email}
            >
              {addingEmail ? "Adding…" : <><PlusCircle size={14} /> Add recipient</>}
            </button>
          </div>
        </div>
      )}

      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>Notification Recipients</h4>
        {recipients.length === 0 ? (
          <p className="text-sm text-muted text-center" style={{ padding: "2rem" }}>No recipients configured.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Enabled</th>
                  {admin && <th style={{ width: 100 }}>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {recipients.map(r => (
                  <tr key={r.id}>
                    {editId === r.id ? (
                      <>
                        <td><input className="form-input text-sm" value={editForm.email} onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))} /></td>
                        <td><input className="form-input text-sm" value={editForm.display_name} onChange={e => setEditForm(f => ({ ...f, display_name: e.target.value }))} /></td>
                        <td>
                          <select className="form-input text-sm" value={editForm.category} onChange={e => setEditForm(f => ({ ...f, category: e.target.value }))}>
                            {Object.entries(categories).map(([id, label]) => (
                              <option key={id} value={id}>{label}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input type="checkbox" checked={editForm.enabled} onChange={e => setEditForm(f => ({ ...f, enabled: e.target.checked }))} />
                        </td>
                        <td>
                          <button className="btn btn-primary btn-sm" onClick={saveEdit}>Save</button>
                          <button className="btn btn-secondary btn-sm ml-1" onClick={() => setEditId(null)}>Cancel</button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td style={{ fontSize: "0.78rem" }}>{r.email}</td>
                        <td style={{ fontSize: "0.78rem" }}>{r.display_name || "—"}</td>
                        <td><span className="badge badge-blue">{categories[r.category] || r.category}</span></td>
                        <td>{r.enabled ? <span className="badge badge-green">Yes</span> : <span className="badge badge-gray">No</span>}</td>
                        {admin && (
                          <td>
                            <button className="btn btn-secondary btn-sm" onClick={() => startEdit(r)}><Pencil size={11} /></button>
                            <button className="btn btn-danger btn-sm ml-1" onClick={() => deleteRecipient(r.id)}><Trash2 size={11} /></button>
                          </td>
                        )}
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {emailLog.length > 0 && (
        <div className="card" style={{ padding: "1.5rem" }}>
          <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>Email Log (recent)</h4>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Sent</th>
                  <th>Type</th>
                  <th>Subject</th>
                  <th>Recipients</th>
                  <th>Status</th>
                  <th>By</th>
                </tr>
              </thead>
              <tbody>
                {emailLog.slice(0, 20).map((row, i) => (
                  <tr key={row.id ?? i}>
                    <td style={{ fontSize: "0.72rem" }}>{row.sent_at || "—"}</td>
                    <td><span className="badge badge-gray">{row.email_type}</span></td>
                    <td style={{ fontSize: "0.72rem", maxWidth: 200 }}>{row.subject}</td>
                    <td style={{ fontSize: "0.72rem" }}>{row.recipients}</td>
                    <td>
                      <span className={`badge badge-${row.status === "sent" ? "green" : "red"}`}>{row.status}</span>
                    </td>
                    <td style={{ fontSize: "0.72rem" }}>{row.triggered_by || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );

  const sessionTab = (
    <div className="layout-split">
      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>Session</h4>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "0.8rem" }}>
          <div><span className="text-muted">Auth session:</span> {session?.has_session ? session.session_id : "None (will be created on save)"}</div>
          <div><span className="text-muted">Token expires:</span> {session?.token_expires_at || "—"}</div>
          {session?.session_created_at && (
            <div><span className="text-muted">Session created:</span> {session.session_created_at}</div>
          )}
        </div>
        <h5 style={{ margin: "1.25rem 0 0.5rem", fontSize: "0.85rem" }}>Live client info (this browser)</h5>
        <pre style={{ fontSize: "0.68rem", background: "var(--bg-hover)", padding: "0.75rem", borderRadius: 8, overflow: "auto", maxHeight: 180 }}>
          {fmtJson(clientInfo)}
        </pre>
        <button className="btn btn-primary btn-sm mt-2" onClick={saveSessionDetails} disabled={savingSession}>
          {savingSession ? "Saving…" : <><Save size={13} /> Save system details</>}
        </button>
      </div>

      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>Stored system details</h4>
        <pre style={{ fontSize: "0.68rem", background: "var(--bg-hover)", padding: "0.75rem", borderRadius: 8, overflow: "auto", maxHeight: 320 }}>
          {session?.stored_system_details ? fmtJson(session.stored_system_details) : "No details saved yet — click Save on the left."}
        </pre>
        <h5 style={{ margin: "1rem 0 0.5rem", fontSize: "0.85rem" }}>Live server info</h5>
        <pre style={{ fontSize: "0.68rem", background: "var(--bg-hover)", padding: "0.75rem", borderRadius: 8, overflow: "auto", maxHeight: 160 }}>
          {fmtJson(session?.live_server_details || {})}
        </pre>
      </div>
    </div>
  );

  const usersTab = admin ? (
    <UsersAdminTab onMessage={(text, type) => setMsg({ text, type })} />
  ) : (
    <div className="card" style={{ padding: "1.5rem" }}>
      <p className="text-sm text-muted">Only administrators can manage users.</p>
    </div>
  );

  const aboutTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: 640 }}>
      <div className="card" style={{ padding: "1.25rem 1.5rem" }}>
        <h4 style={{ margin: "0 0 0.5rem", fontWeight: 700 }}>Team user guide</h4>
        <p className="text-sm text-muted" style={{ margin: "0 0 1rem", lineHeight: 1.6 }}>
          New to Planning Suite? Read the step-by-step guide: weekly workflow, page overview, roles, and troubleshooting.
        </p>
        <Link href="/about" className="btn btn-primary btn-sm">
          <BookOpen size={14} /> Open About &amp; User Guide
        </Link>
      </div>
      <div className="card" style={{ padding: "1.5rem" }}>
      <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>System information</h4>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", fontSize: "0.84rem" }}>
        <div><span className="text-muted">Application:</span> {boot?.about?.app_name || "Planning Suite"}</div>
        <div><span className="text-muted">API version:</span> {boot?.about?.api_version || "2.0.0"}</div>
        <div><span className="text-muted">Environment:</span> {String(boot?.about?.environment ?? env?.app_env ?? "—")}</div>
        <div><span className="text-muted">Database:</span> {String(boot?.about?.database_backend ?? env?.database_backend ?? "—")}</div>
      </div>
      {env && (
        <div style={{ marginTop: "1.5rem" }}>
          <h5 style={{ margin: "0 0 0.75rem", fontSize: "0.9rem" }}>Environment checks</h5>
          {[
            { label: "Production mode", value: env.is_production ? "Yes" : "No", badge: env.is_production ? "green" : "yellow" },
            { label: "SMTP", value: env.smtp_configured ? "Configured" : "Missing", badge: env.smtp_configured ? "green" : "red" },
            { label: "Google credentials", value: env.google_credentials_path ? "Configured" : "Missing", badge: env.google_credentials_path ? "green" : "red" },
            { label: "Pipeline params sheet", value: env.pipeline_params_sheet_url ? "Configured" : "Missing", badge: env.pipeline_params_sheet_url ? "green" : "yellow" },
          ].map(row => (
            <div key={row.label} style={{ display: "flex", justifyContent: "space-between", padding: "0.5rem 0", borderBottom: "1px solid var(--border)" }}>
              <span className="text-sm text-muted">{row.label}</span>
              <span className={`badge badge-${row.badge}`}>{String(row.value)}</span>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-muted mt-3" style={{ lineHeight: 1.6 }}>
        Backend parameters are configured via the server <code>.env</code> file. Restart the FastAPI server after changes.
        See <code>DEPLOY.md</code> and <code>OPS_RUNBOOK.md</code> in the repository for production setup.
      </p>
      </div>
    </div>
  );

  const mainTabs = [
    { id: "profile", label: <><User size={14} /> Profile</>, content: profileTab },
    { id: "preferences", label: <><Settings size={14} /> Preferences</>, content: preferencesTab },
    ...(admin ? [{ id: "users", label: <><Users size={14} /> Users</>, content: usersTab }] : []),
    { id: "email", label: <><Mail size={14} /> Email Settings</>, content: emailTab },
    { id: "session", label: <><Monitor size={14} /> Session</>, content: sessionTab },
    { id: "about", label: <><Info size={14} /> About</>, content: aboutTab },
  ];

  return (
    <AppShell
      title="Settings"
      subtitle="Profile, preferences, email, session & environment"
      actions={
        <button className="btn btn-secondary btn-sm" onClick={() => loadBootstrap(true)} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      }
    >
      {msg.text && (
        <div className={`alert alert-${msg.type}`} style={{ marginBottom: "1.25rem" }}>{msg.text}</div>
      )}
      {loading && !boot ? (
        <div className="text-sm text-muted">Loading settings…</div>
      ) : (
        <>
          {loading && (
            <div className="text-xs text-muted mb-2" style={{ opacity: 0.7 }}>Refreshing…</div>
          )}
          <Tabs tabs={mainTabs} defaultTab="profile" />
        </>
      )}
    </AppShell>
  );
}
