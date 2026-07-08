"use client";

import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { PlusCircle, Pencil, KeyRound, UserX, UserCheck, RefreshCw, Send, Mail } from "lucide-react";

type AdminUser = {
  id: number;
  username: string;
  full_name?: string | null;
  email?: string | null;
  role: string;
  is_active: boolean | number;
  created_at?: string | null;
  last_login?: string | null;
};

const ROLES = ["admin", "planner", "viewer", "product"] as const;

type Props = {
  onMessage: (text: string, type: "success" | "danger") => void;
};

export default function UsersAdminTab({ onMessage }: Props) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [sendingMail, setSendingMail] = useState<number | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [resetId, setResetId] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const [newUser, setNewUser] = useState({
    username: "",
    password: "",
    full_name: "",
    email: "",
    role: "planner",
  });

  const [editForm, setEditForm] = useState({
    full_name: "",
    email: "",
    role: "planner",
    is_active: true,
  });

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get<{ users: AdminUser[] }>("/api/settings/users");
      setUsers(data.users || []);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      onMessage(err?.response?.data?.detail || "Failed to load users", "danger");
    }
    setLoading(false);
  }, [onMessage]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  const createUser = async () => {
    if (!newUser.username || !newUser.password) return;
    setCreating(true);
    try {
      await api.post("/api/settings/users", newUser);
      onMessage(`User ${newUser.username} created.`, "success");
      setNewUser({ username: "", password: "", full_name: "", email: "", role: "planner" });
      await loadUsers();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      onMessage(err?.response?.data?.detail || "Create failed", "danger");
    }
    setCreating(false);
  };

  const startEdit = (u: AdminUser) => {
    setEditId(u.id);
    setEditForm({
      full_name: u.full_name || "",
      email: u.email || "",
      role: u.role,
      is_active: Boolean(u.is_active),
    });
    setResetId(null);
  };

  const saveEdit = async () => {
    if (editId == null) return;
    try {
      await api.patch(`/api/settings/users/${editId}`, editForm);
      onMessage("User updated.", "success");
      setEditId(null);
      await loadUsers();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      onMessage(err?.response?.data?.detail || "Update failed", "danger");
    }
  };

  const resetPassword = async () => {
    if (resetId == null || !newPassword) return;
    try {
      await api.post(`/api/settings/users/${resetId}/reset-password`, { password: newPassword });
      onMessage("Password reset.", "success");
      setResetId(null);
      setNewPassword("");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      onMessage(err?.response?.data?.detail || "Reset failed", "danger");
    }
  };

  const toggleActive = async (u: AdminUser) => {
    try {
      await api.patch(`/api/settings/users/${u.id}`, { is_active: !Boolean(u.is_active) });
      onMessage(Boolean(u.is_active) ? "User deactivated." : "User activated.", "success");
      await loadUsers();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      onMessage(err?.response?.data?.detail || "Update failed", "danger");
    }
  };

  const sendTestMail = async (u: AdminUser) => {
    if (!u.email) return;
    setSendingMail(u.id);
    try {
      await api.post("/api/settings/test-email", {
        to_email: u.email,
        message: `Hello ${u.full_name || u.username}, this is a test email sent from the admin panel to verify your notifications status.`,
      });
      onMessage(`Test email sent successfully to ${u.email}`, "success");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      onMessage(err?.response?.data?.detail || "Failed to send test email", "danger");
    }
    setSendingMail(null);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Tab Header Controls */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-color)", paddingBottom: "1rem" }}>
        <div>
          <h3 style={{ margin: "0 0 0.25rem", fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>User Directory</h3>
          <p className="text-sm text-muted" style={{ margin: 0 }}>
            Create accounts, assign system roles, manage activations, and reset credentials.
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={() => loadUsers()} disabled={loading} style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh List
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: resetId ? "1fr 1fr" : "3fr 1fr", gap: "1.5rem", alignItems: "start" }}>
        
        {/* Users Table / main list */}
        <div className="card" style={{ padding: "1.5rem", background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "var(--radius-lg)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
            <h4 style={{ margin: 0, fontWeight: 700, fontSize: "0.95rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>Registered Accounts</h4>
            <span style={{ fontSize: "0.75rem", background: "var(--bg-accent)", padding: "2px 8px", borderRadius: "10px", fontWeight: 600, color: "var(--text-primary)" }}>
              {users.length} Users Total
            </span>
          </div>

          {loading && users.length === 0 ? (
            <div style={{ padding: "3rem 0", textAlign: "center" }}>
              <span className="spinner" style={{ width: 24, height: 24, margin: "0 auto 1rem" }} />
              <p className="text-sm text-muted" style={{ margin: 0 }}>Loading user accounts...</p>
            </div>
          ) : users.length === 0 ? (
            <div style={{ padding: "3rem 0", textAlign: "center", border: "1px dashed var(--border-color)", borderRadius: "var(--radius-md)" }}>
              <p className="text-sm text-muted" style={{ margin: 0 }}>No registered users found.</p>
            </div>
          ) : (
            <div className="table-wrap" style={{ margin: 0, overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--border-color)" }}>
                    <th style={{ padding: "10px 12px", fontWeight: 600, fontSize: "0.78rem", color: "var(--text-secondary)" }}>Username</th>
                    <th style={{ padding: "10px 12px", fontWeight: 600, fontSize: "0.78rem", color: "var(--text-secondary)" }}>Display Name</th>
                    <th style={{ padding: "10px 12px", fontWeight: 600, fontSize: "0.78rem", color: "var(--text-secondary)" }}>Email Address</th>
                    <th style={{ padding: "10px 12px", fontWeight: 600, fontSize: "0.78rem", color: "var(--text-secondary)" }}>System Role</th>
                    <th style={{ padding: "10px 12px", fontWeight: 600, fontSize: "0.78rem", color: "var(--text-secondary)" }}>Status</th>
                    <th style={{ padding: "10px 12px", fontWeight: 600, fontSize: "0.78rem", color: "var(--text-secondary)" }}>Last Login</th>
                    <th style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, fontSize: "0.78rem", color: "var(--text-secondary)" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id} style={{ borderBottom: "1px solid var(--border-color)", transition: "background 0.2s" }} className="hover-row">
                      {editId === u.id ? (
                        <>
                          <td style={{ padding: "12px", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-primary)" }}>{u.username}</td>
                          <td style={{ padding: "8px" }}>
                            <input
                              className="form-input text-sm"
                              value={editForm.full_name}
                              onChange={e => setEditForm(f => ({ ...f, full_name: e.target.value }))}
                              style={{ padding: "4px 8px", minWidth: "120px" }}
                            />
                          </td>
                          <td style={{ padding: "8px" }}>
                            <input
                              type="email"
                              className="form-input text-sm"
                              value={editForm.email}
                              onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))}
                              style={{ padding: "4px 8px", minWidth: "160px" }}
                            />
                          </td>
                          <td style={{ padding: "8px" }}>
                            <select
                              className="form-input text-sm"
                              value={editForm.role}
                              onChange={e => setEditForm(f => ({ ...f, role: e.target.value }))}
                              style={{ padding: "4px 24px 4px 8px", minWidth: "100px" }}
                            >
                              {ROLES.map(r => (
                                <option key={r} value={r}>{r}</option>
                              ))}
                            </select>
                          </td>
                          <td style={{ padding: "8px", verticalAlign: "middle" }}>
                            <label style={{ display: "inline-flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                              <input
                                type="checkbox"
                                checked={editForm.is_active}
                                onChange={e => setEditForm(f => ({ ...f, is_active: e.target.checked }))}
                                style={{ accentColor: "var(--blue)" }}
                              />
                              <span style={{ fontSize: "0.75rem" }}>Active</span>
                            </label>
                          </td>
                          <td style={{ padding: "12px", fontSize: "0.72rem", color: "var(--text-muted)" }}>{u.last_login || "—"}</td>
                          <td style={{ padding: "8px", textAlign: "right" }}>
                            <div style={{ display: "inline-flex", gap: "6px" }}>
                              <button className="btn btn-primary btn-sm" onClick={saveEdit} style={{ padding: "2px 8px", fontSize: "0.72rem" }}>Save</button>
                              <button className="btn btn-secondary btn-sm" onClick={() => setEditId(null)} style={{ padding: "2px 8px", fontSize: "0.72rem" }}>Cancel</button>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td style={{ padding: "12px", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-primary)" }}>{u.username}</td>
                          <td style={{ padding: "12px", fontSize: "0.78rem", color: "var(--text-primary)" }}>{u.full_name || "—"}</td>
                          <td style={{ padding: "12px", fontSize: "0.78rem", color: "var(--text-secondary)" }}>{u.email || "—"}</td>
                          <td style={{ padding: "12px" }}>
                            <span className={`badge ${u.role === "admin" ? "badge-blue" : u.role === "planner" ? "badge-green" : "badge-gray"}`} style={{ textTransform: "capitalize", padding: "2px 6px" }}>
                              {u.role}
                            </span>
                          </td>
                          <td style={{ padding: "12px" }}>
                            {Boolean(u.is_active) ? (
                              <span className="badge badge-green" style={{ padding: "2px 6px" }}>Active</span>
                            ) : (
                              <span className="badge badge-gray" style={{ padding: "2px 6px" }}>Inactive</span>
                            )}
                          </td>
                          <td style={{ padding: "12px", fontSize: "0.72rem", color: "var(--text-muted)" }}>{u.last_login || "—"}</td>
                          <td style={{ padding: "12px", textAlign: "right" }}>
                            <div style={{ display: "inline-flex", gap: "6px", justifyContent: "flex-end" }}>
                              {u.email && (
                                <button
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => sendTestMail(u)}
                                  disabled={sendingMail === u.id}
                                  title="Send Test Email"
                                  style={{ padding: "4px", minWidth: "26px", height: "26px" }}
                                >
                                  {sendingMail === u.id ? <span className="spinner" style={{ width: 10, height: 10 }} /> : <Mail size={12} />}
                                </button>
                              )}
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => startEdit(u)}
                                title="Edit Profile"
                                style={{ padding: "4px", minWidth: "26px", height: "26px" }}
                              >
                                <Pencil size={12} />
                              </button>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => { setResetId(u.id); setEditId(null); setNewPassword(""); }}
                                title="Reset Password"
                                style={{ padding: "4px", minWidth: "26px", height: "26px" }}
                              >
                                <KeyRound size={12} />
                              </button>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => toggleActive(u)}
                                title={Boolean(u.is_active) ? "Deactivate User" : "Activate User"}
                                style={{ padding: "4px", minWidth: "26px", height: "26px", color: Boolean(u.is_active) ? "var(--red)" : "var(--green)" }}
                              >
                                {Boolean(u.is_active) ? <UserX size={12} /> : <UserCheck size={12} />}
                              </button>
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Sidebar Cards (Add User / Password Reset) */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          
          {/* Create User Card */}
          <div className="card" style={{ padding: "1.5rem", background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "var(--radius-lg)" }}>
            <h4 style={{ margin: "0 0 1rem", fontWeight: 700, fontSize: "0.9rem", color: "var(--text-primary)" }}>Add New User</h4>
            
            <div className="form-group" style={{ marginBottom: "0.85rem" }}>
              <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>Username *</label>
              <input
                className="form-input text-sm"
                placeholder="john_doe"
                value={newUser.username}
                onChange={e => setNewUser(n => ({ ...n, username: e.target.value }))}
                style={{ padding: "6px 10px" }}
              />
            </div>
            
            <div className="form-group" style={{ marginBottom: "0.85rem" }}>
              <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>Password *</label>
              <input
                type="password"
                className="form-input text-sm"
                placeholder="••••••••"
                value={newUser.password}
                onChange={e => setNewUser(n => ({ ...n, password: e.target.value }))}
                style={{ padding: "6px 10px" }}
              />
            </div>
            
            <div className="form-group" style={{ marginBottom: "0.85rem" }}>
              <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>Full Name</label>
              <input
                className="form-input text-sm"
                placeholder="John Doe"
                value={newUser.full_name}
                onChange={e => setNewUser(n => ({ ...n, full_name: e.target.value }))}
                style={{ padding: "6px 10px" }}
              />
            </div>
            
            <div className="form-group" style={{ marginBottom: "0.85rem" }}>
              <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>Email Address</label>
              <input
                type="email"
                className="form-input text-sm"
                placeholder="john@company.com"
                value={newUser.email}
                onChange={e => setNewUser(n => ({ ...n, email: e.target.value }))}
                style={{ padding: "6px 10px" }}
              />
            </div>
            
            <div className="form-group" style={{ marginBottom: "1.25rem" }}>
              <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>Role</label>
              <select
                className="form-input text-sm"
                value={newUser.role}
                onChange={e => setNewUser(n => ({ ...n, role: e.target.value }))}
                style={{ padding: "6px 24px 6px 10px" }}
              >
                {ROLES.map(r => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            
            <button
              className="btn btn-primary text-sm w-full"
              onClick={createUser}
              disabled={creating || !newUser.username || !newUser.password}
              style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "6px", padding: "8px 12px" }}
            >
              {creating ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <><PlusCircle size={14} /> Create User</>}
            </button>
          </div>

          {/* Reset Password Card */}
          {resetId != null && (
            <div className="card animate-fade-in" style={{ padding: "1.5rem", background: "var(--bg-card)", border: "1px solid var(--border-accent)", borderRadius: "var(--radius-lg)" }}>
              <h4 style={{ margin: "0 0 1rem", fontWeight: 700, fontSize: "0.9rem", color: "var(--text-primary)" }}>Reset Password</h4>
              
              <div className="form-group" style={{ marginBottom: "1rem" }}>
                <label className="form-label" style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>New Password</label>
                <input
                  type="password"
                  className="form-input text-sm"
                  placeholder="••••••••"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  style={{ padding: "6px 10px" }}
                />
              </div>
              
              <div style={{ display: "flex", gap: "8px" }}>
                <button className="btn btn-primary btn-sm w-full" onClick={resetPassword} disabled={!newPassword} style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "4px" }}>
                  <KeyRound size={12} /> Save
                </button>
                <button className="btn btn-secondary btn-sm w-full" onClick={() => { setResetId(null); setNewPassword(""); }}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
