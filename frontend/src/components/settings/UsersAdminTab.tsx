"use client";

import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { PlusCircle, Pencil, KeyRound, UserX, UserCheck, RefreshCw } from "lucide-react";

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

const ROLES = ["admin", "planner", "viewer"] as const;

type Props = {
  onMessage: (text: string, type: "success" | "danger") => void;
};

export default function UsersAdminTab({ onMessage }: Props) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p className="text-sm text-muted" style={{ margin: 0 }}>
          Create accounts, assign roles, deactivate users, and reset passwords.
        </p>
        <button className="btn btn-secondary btn-sm" onClick={() => loadUsers()} disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      <div className="layout-split">
        <div className="card" style={{ padding: "1.5rem" }}>
          <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>Add User</h4>
          <div className="form-group">
            <label className="form-label">Username *</label>
            <input
              className="form-input text-sm"
              value={newUser.username}
              onChange={e => setNewUser(n => ({ ...n, username: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Password *</label>
            <input
              type="password"
              className="form-input text-sm"
              value={newUser.password}
              onChange={e => setNewUser(n => ({ ...n, password: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Full name</label>
            <input
              className="form-input text-sm"
              value={newUser.full_name}
              onChange={e => setNewUser(n => ({ ...n, full_name: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Email</label>
            <input
              type="email"
              className="form-input text-sm"
              value={newUser.email}
              onChange={e => setNewUser(n => ({ ...n, email: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Role</label>
            <select
              className="form-input text-sm"
              value={newUser.role}
              onChange={e => setNewUser(n => ({ ...n, role: e.target.value }))}
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
          >
            {creating ? "Creating…" : <><PlusCircle size={14} /> Create user</>}
          </button>
        </div>

        {resetId != null && (
          <div className="card" style={{ padding: "1.5rem" }}>
            <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>Reset Password</h4>
            <div className="form-group">
              <label className="form-label">New password</label>
              <input
                type="password"
                className="form-input text-sm"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
              />
            </div>
            <button className="btn btn-primary btn-sm" onClick={resetPassword} disabled={!newPassword}>
              <KeyRound size={13} /> Save password
            </button>
            <button className="btn btn-secondary btn-sm ml-2" onClick={() => { setResetId(null); setNewPassword(""); }}>
              Cancel
            </button>
          </div>
        )}
      </div>

      <div className="card" style={{ padding: "1.5rem" }}>
        <h4 style={{ margin: "0 0 1rem", fontWeight: 700 }}>All Users</h4>
        {loading && users.length === 0 ? (
          <p className="text-sm text-muted">Loading users…</p>
        ) : users.length === 0 ? (
          <p className="text-sm text-muted">No users found.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last login</th>
                  <th style={{ width: 140 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id}>
                    {editId === u.id ? (
                      <>
                        <td style={{ fontSize: "0.78rem" }}>{u.username}</td>
                        <td>
                          <input
                            className="form-input text-sm"
                            value={editForm.full_name}
                            onChange={e => setEditForm(f => ({ ...f, full_name: e.target.value }))}
                          />
                        </td>
                        <td>
                          <input
                            className="form-input text-sm"
                            value={editForm.email}
                            onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))}
                          />
                        </td>
                        <td>
                          <select
                            className="form-input text-sm"
                            value={editForm.role}
                            onChange={e => setEditForm(f => ({ ...f, role: e.target.value }))}
                          >
                            {ROLES.map(r => (
                              <option key={r} value={r}>{r}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <input
                            type="checkbox"
                            checked={editForm.is_active}
                            onChange={e => setEditForm(f => ({ ...f, is_active: e.target.checked }))}
                          />
                        </td>
                        <td style={{ fontSize: "0.72rem" }}>{u.last_login || "—"}</td>
                        <td>
                          <button className="btn btn-primary btn-sm" onClick={saveEdit}>Save</button>
                          <button className="btn btn-secondary btn-sm ml-1" onClick={() => setEditId(null)}>Cancel</button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td style={{ fontSize: "0.78rem", fontWeight: 600 }}>{u.username}</td>
                        <td style={{ fontSize: "0.78rem" }}>{u.full_name || "—"}</td>
                        <td style={{ fontSize: "0.78rem" }}>{u.email || "—"}</td>
                        <td><span className="badge badge-blue">{u.role}</span></td>
                        <td>
                          {Boolean(u.is_active) ? (
                            <span className="badge badge-green">Active</span>
                          ) : (
                            <span className="badge badge-gray">Inactive</span>
                          )}
                        </td>
                        <td style={{ fontSize: "0.72rem" }}>{u.last_login || "—"}</td>
                        <td>
                          <button className="btn btn-secondary btn-sm" onClick={() => startEdit(u)} title="Edit">
                            <Pencil size={11} />
                          </button>
                          <button
                            className="btn btn-secondary btn-sm ml-1"
                            onClick={() => { setResetId(u.id); setEditId(null); setNewPassword(""); }}
                            title="Reset password"
                          >
                            <KeyRound size={11} />
                          </button>
                          <button
                            className="btn btn-secondary btn-sm ml-1"
                            onClick={() => toggleActive(u)}
                            title={Boolean(u.is_active) ? "Deactivate" : "Activate"}
                          >
                            {Boolean(u.is_active) ? <UserX size={11} /> : <UserCheck size={11} />}
                          </button>
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
    </div>
  );
}
