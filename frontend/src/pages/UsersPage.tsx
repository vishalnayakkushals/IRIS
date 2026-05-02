import { useEffect, useState } from "react";
import {
  adminListUsers,
  adminCreateUser,
  adminUpdateUser,
  adminDeleteUser,
  adminResetPassword,
  adminBulkResetPassword,
  adminListRoles,
  adminListStores,
  adminReplaceStoreAccess,
} from "../api/client";
import { Card, Title, Text, Badge } from "@tremor/react";
import { Plus, Pencil, Trash2, X, Check, Eye, EyeOff, RefreshCw } from "lucide-react";

const DEFAULT_PASSWORD = "user12345";

function StoreSearchSelect({ stores, value, onChange }: {
  stores: any[]; value: string; onChange: (v: string) => void;
}) {
  const [search, setSearch] = useState("");
  const filtered = stores.filter((s) =>
    !search || `${s.store_id} ${s.store_name}`.toLowerCase().includes(search.toLowerCase())
  );
  return (
    <div className="space-y-1">
      <input
        className="iris-input text-xs"
        placeholder="Search store…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <select
        className="iris-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        size={Math.min(5, filtered.length + 1)}
      >
        <option value="">— none —</option>
        {filtered.map((s) => (
          <option key={s.store_id} value={s.store_id}>
            {s.store_id} — {s.store_name}
          </option>
        ))}
      </select>
    </div>
  );
}

function UserForm({
  initial, roles, stores, onSave, onCancel, isNew,
}: {
  initial: any; roles: any[]; stores: any[]; onSave: (v: any) => Promise<void>; onCancel: () => void; isNew: boolean;
}) {
  const [v, setV] = useState({
    email: initial.email || "",
    full_name: initial.full_name || "",
    password: isNew ? DEFAULT_PASSWORD : "",
    store_id: initial.store_id || "",
    is_active: initial.is_active !== false,
    role_names: initial.roles || [],
  });
  const [saving, setSaving] = useState(false);
  const [showPw, setShowPw] = useState(true);

  function toggleRole(r: string) {
    setV((prev) => ({
      ...prev,
      role_names: prev.role_names.includes(r)
        ? prev.role_names.filter((x: string) => x !== r)
        : [...prev.role_names, r],
    }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try { await onSave(v); } finally { setSaving(false); }
  }

  return (
    <form onSubmit={submit} className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
        {isNew ? "New User" : `Editing ${v.email}`}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="iris-label">Email *</label>
          <input type="email" required disabled={!isNew} className="iris-input" value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} />
        </div>
        <div>
          <label className="iris-label">Full Name *</label>
          <input required className="iris-input" value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} />
        </div>
        {isNew && (
          <div>
            <label className="iris-label">Password *</label>
            <div className="relative">
              <input
                type={showPw ? "text" : "password"}
                required
                className="iris-input pr-10"
                value={v.password}
                onChange={(e) => setV({ ...v, password: e.target.value })}
              />
              <button
                type="button"
                onClick={() => setShowPw((p) => !p)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              >
                {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-1">Default: {DEFAULT_PASSWORD}</p>
          </div>
        )}
        <div>
          <label className="iris-label">Default Store</label>
          <StoreSearchSelect stores={stores} value={v.store_id} onChange={(val) => setV({ ...v, store_id: val })} />
        </div>
        <div className="flex items-center gap-2 pt-2">
          <input type="checkbox" id="active" checked={v.is_active} onChange={(e) => setV({ ...v, is_active: e.target.checked })} className="rounded border-slate-300 text-blue-600" />
          <label htmlFor="active" className="text-sm text-slate-600">Active</label>
        </div>
      </div>
      <div>
        <label className="iris-label">Roles</label>
        <div className="flex flex-wrap gap-2 mt-1">
          {roles.map((r) => (
            <button
              key={r.role_name}
              type="button"
              onClick={() => toggleRole(r.role_name)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${v.role_names.includes(r.role_name) ? "bg-blue-600 text-white border-blue-600" : "text-slate-600 border-slate-300 hover:border-blue-400 hover:text-blue-600"}`}
            >
              {r.role_name}
            </button>
          ))}
          {roles.length === 0 && <span className="text-xs text-slate-400">No roles defined yet</span>}
        </div>
      </div>
      <div className="flex gap-2 pt-1 border-t border-slate-100">
        <button type="submit" disabled={saving} className="iris-btn-primary">
          <Check size={14} />
          {saving ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onCancel} className="iris-btn-secondary">
          <X size={14} />
          Cancel
        </button>
      </div>
    </form>
  );
}

function PasswordCell({ hint, email, onReset }: { hint: string; email: string; onReset: (email: string, pw: string) => Promise<void> }) {
  const [show, setShow] = useState(false);
  const [resetting, setResetting] = useState(false);

  async function resetToDefault() {
    setResetting(true);
    try { await onReset(email, DEFAULT_PASSWORD); } finally { setResetting(false); }
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="font-mono text-xs text-slate-600">
        {show ? (hint || "—") : (hint ? "••••••••" : "—")}
      </span>
      {hint && (
        <button onClick={() => setShow((p) => !p)} className="text-slate-300 hover:text-slate-500" title={show ? "Hide" : "Show"}>
          {show ? <EyeOff size={11} /> : <Eye size={11} />}
        </button>
      )}
      <button
        onClick={resetToDefault}
        disabled={resetting}
        title="Reset to user12345"
        className="text-slate-300 hover:text-amber-500 disabled:opacity-40"
      >
        <RefreshCw size={11} />
      </button>
    </div>
  );
}

export default function UsersPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [roles, setRoles] = useState<any[]>([]);
  const [stores, setStores] = useState<any[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [toast, setToast] = useState("");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  async function load() {
    const [u, r, s] = await Promise.all([adminListUsers(), adminListRoles(), adminListStores()]);
    setUsers(u.data);
    setRoles(r.data);
    setStores(s.data);
  }

  useEffect(() => { load(); }, []);

  async function handleCreate(v: any) {
    try {
      await adminCreateUser(v);
      // Auto-grant store access for the assigned store
      if (v.store_id) {
        await adminReplaceStoreAccess(v.email, [v.store_id]).catch(() => {});
      }
      setShowNew(false);
      flash("User created");
      load();
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Create failed");
    }
  }

  async function handleUpdate(v: any) {
    try {
      await adminUpdateUser(v.email, v);
      setEditing(null);
      flash("User updated");
      load();
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Update failed");
    }
  }

  async function handleDelete(email: string) {
    if (!confirm(`Delete user ${email}?`)) return;
    try {
      await adminDeleteUser(email);
      flash("Deleted");
      load();
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Delete failed");
    }
  }

  async function handleResetPassword(email: string, pw: string) {
    try {
      await adminResetPassword(email, pw);
      flash(`Password reset for ${email}`);
      load();
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Reset failed");
    }
  }

  async function handleBulkReset() {
    if (!confirm(`Reset ALL users' passwords to "${DEFAULT_PASSWORD}"?`)) return;
    try {
      const res = await adminBulkResetPassword(DEFAULT_PASSWORD);
      flash(`Reset ${res.data.reset} user(s) to ${DEFAULT_PASSWORD}`);
      load();
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Bulk reset failed");
    }
  }

  return (
    <div className="space-y-6">
      {toast && <div className="iris-toast">{toast}</div>}

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div><Title>Users</Title><Text>Manage user accounts, roles, and store assignments.</Text></div>
        <div className="flex gap-2">
          <button onClick={handleBulkReset} className="iris-btn-secondary" title={`Reset all passwords to ${DEFAULT_PASSWORD}`}>
            <RefreshCw size={14} /> Reset All Passwords
          </button>
          <button onClick={() => { setShowNew(true); setEditing(null); }} className="iris-btn-primary">
            <Plus size={15} /> Add User
          </button>
        </div>
      </div>

      {showNew && (
        <UserForm initial={{ is_active: true }} roles={roles} stores={stores} onSave={handleCreate} onCancel={() => setShowNew(false)} isNew />
      )}

      <Card className="p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
                <th className="px-5 py-3">Email</th>
                <th className="px-5 py-3">Name</th>
                <th className="px-5 py-3">Password</th>
                <th className="px-5 py-3">Store</th>
                <th className="px-5 py-3">Roles</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users.map((u) => (
                <>
                  <tr key={u.email} className="hover:bg-slate-50/50">
                    <td className="px-5 py-3 text-slate-700 font-medium text-xs">{u.email}</td>
                    <td className="px-5 py-3 text-sm">{u.full_name}</td>
                    <td className="px-5 py-3">
                      <PasswordCell hint={u.password_hint || ""} email={u.email} onReset={handleResetPassword} />
                    </td>
                    <td className="px-5 py-3 text-slate-500 text-xs font-mono">{u.store_id || "—"}</td>
                    <td className="px-5 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(u.roles || []).map((r: string) => <Badge key={r} color="blue">{r}</Badge>)}
                        {!u.roles?.length && <span className="text-slate-400 text-xs">—</span>}
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <Badge color={u.is_active ? "emerald" : "slate"}>{u.is_active ? "Active" : "Inactive"}</Badge>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex gap-2">
                        <button onClick={() => setEditing(editing === u.email ? null : u.email)} className="text-slate-400 hover:text-blue-600 transition-colors" title="Edit"><Pencil size={14} /></button>
                        <button onClick={() => handleDelete(u.email)} className="text-slate-400 hover:text-rose-600 transition-colors" title="Delete"><Trash2 size={14} /></button>
                      </div>
                    </td>
                  </tr>
                  {editing === u.email && (
                    <tr key={`edit-${u.email}`}>
                      <td colSpan={7} className="px-5 py-3">
                        <UserForm initial={u} roles={roles} stores={stores} onSave={handleUpdate} onCancel={() => setEditing(null)} isNew={false} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
              {users.length === 0 && <tr><td colSpan={7} className="text-center py-12 text-gray-400 text-sm">No users.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
