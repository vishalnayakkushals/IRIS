import { useEffect, useState } from "react";
import {
  adminListUsers,
  adminCreateUser,
  adminUpdateUser,
  adminDeleteUser,
  adminResetPassword,
  adminListRoles,
  adminListStores,
} from "../api/client";
import { Card, Title, Text, Button, Badge } from "@tremor/react";
import { Plus, Pencil, Trash2, Key, X, Check } from "lucide-react";

function UserForm({
  initial,
  roles,
  stores,
  onSave,
  onCancel,
  isNew,
}: {
  initial: any;
  roles: any[];
  stores: any[];
  onSave: (v: any) => Promise<void>;
  onCancel: () => void;
  isNew: boolean;
}) {
  const [v, setV] = useState({
    email: initial.email || "",
    full_name: initial.full_name || "",
    password: "",
    store_id: initial.store_id || "",
    is_active: initial.is_active !== false,
    role_names: initial.roles || [],
  });
  const [saving, setSaving] = useState(false);

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
    <form onSubmit={submit} className="bg-slate-50 border rounded-lg p-5 space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Email *</label>
          <input type="email" required disabled={!isNew} className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Full Name *</label>
          <input required className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} />
        </div>
        {isNew && (
          <div>
            <label className="block text-xs text-slate-500 mb-1">Password *</label>
            <input type="password" required className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" value={v.password} onChange={(e) => setV({ ...v, password: e.target.value })} />
          </div>
        )}
        <div>
          <label className="block text-xs text-slate-500 mb-1">Default Store</label>
          <select className="w-full border rounded px-3 py-2 text-sm" value={v.store_id} onChange={(e) => setV({ ...v, store_id: e.target.value })}>
            <option value="">— none —</option>
            {stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2 pt-5">
          <input type="checkbox" id="active" checked={v.is_active} onChange={(e) => setV({ ...v, is_active: e.target.checked })} />
          <label htmlFor="active" className="text-sm text-slate-600">Active</label>
        </div>
      </div>
      <div>
        <label className="block text-xs text-slate-500 mb-2">Roles</label>
        <div className="flex flex-wrap gap-2">
          {roles.map((r) => (
            <button
              key={r.role_name}
              type="button"
              onClick={() => toggleRole(r.role_name)}
              className={`px-3 py-1 rounded-full text-xs border transition-colors ${v.role_names.includes(r.role_name) ? "bg-blue-600 text-white border-blue-600" : "text-slate-600 border-slate-300 hover:border-blue-400"}`}
            >
              {r.role_name}
            </button>
          ))}
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="xs" color="blue" loading={saving} icon={Check}>Save</Button>
        <Button type="button" size="xs" color="slate" variant="secondary" onClick={onCancel} icon={X}>Cancel</Button>
      </div>
    </form>
  );
}

function PasswordResetModal({ email, onClose }: { email: string; onClose: () => void }) {
  const [pw, setPw] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await adminResetPassword(email, pw);
      setDone(true);
      setTimeout(onClose, 1500);
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm space-y-4">
        <h3 className="font-semibold text-slate-800">Reset Password</h3>
        <p className="text-sm text-slate-500">{email}</p>
        {done ? (
          <p className="text-emerald-600 text-sm font-medium">Password updated!</p>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <input type="password" required placeholder="New password" className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" value={pw} onChange={(e) => setPw(e.target.value)} />
            <div className="flex gap-2">
              <Button type="submit" size="xs" color="blue" loading={saving}>Set Password</Button>
              <Button type="button" size="xs" color="slate" variant="secondary" onClick={onClose}>Cancel</Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default function UsersPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [roles, setRoles] = useState<any[]>([]);
  const [stores, setStores] = useState<any[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [resetting, setResetting] = useState<string | null>(null);
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
    await adminCreateUser(v);
    setShowNew(false);
    flash("User created");
    load();
  }

  async function handleUpdate(v: any) {
    await adminUpdateUser(v.email, v);
    setEditing(null);
    flash("User updated");
    load();
  }

  async function handleDelete(email: string) {
    if (!confirm(`Delete user ${email}?`)) return;
    await adminDeleteUser(email);
    flash("Deleted");
    load();
  }

  return (
    <div className="space-y-6">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}
      {resetting && <PasswordResetModal email={resetting} onClose={() => setResetting(null)} />}

      <div className="flex items-center justify-between">
        <div><Title>Users</Title><Text>Manage user accounts, roles, and store assignments.</Text></div>
        <Button size="sm" icon={Plus} onClick={() => setShowNew(true)}>Add User</Button>
      </div>

      {showNew && (
        <UserForm initial={{}} roles={roles} stores={stores} onSave={handleCreate} onCancel={() => setShowNew(false)} isNew />
      )}

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
              <th className="px-5 py-3">Email</th>
              <th className="px-5 py-3">Name</th>
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
                  <td className="px-5 py-3 text-slate-700 font-medium">{u.email}</td>
                  <td className="px-5 py-3">{u.full_name}</td>
                  <td className="px-5 py-3 text-slate-500 text-xs">{u.store_id || "—"}</td>
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
                      <button onClick={() => setEditing(editing === u.email ? null : u.email)} className="text-slate-400 hover:text-blue-600" title="Edit"><Pencil size={14} /></button>
                      <button onClick={() => setResetting(u.email)} className="text-slate-400 hover:text-amber-600" title="Reset Password"><Key size={14} /></button>
                      <button onClick={() => handleDelete(u.email)} className="text-slate-400 hover:text-rose-600" title="Delete"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
                {editing === u.email && (
                  <tr key={`edit-${u.email}`}>
                    <td colSpan={6} className="px-5 py-3">
                      <UserForm initial={u} roles={roles} stores={stores} onSave={handleUpdate} onCancel={() => setEditing(null)} isNew={false} />
                    </td>
                  </tr>
                )}
              </>
            ))}
            {users.length === 0 && <tr><td colSpan={6} className="text-center py-12 text-gray-400 text-sm">No users.</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
