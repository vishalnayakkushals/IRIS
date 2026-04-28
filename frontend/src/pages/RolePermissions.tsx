import { useEffect, useState } from "react";
import {
  adminListRoles,
  adminCreateRole,
  adminDeleteRole,
  adminSetPermissions,
  adminListPermissionCodes,
} from "../api/client";
import { Card, Title, Text, Button } from "@tremor/react";
import { Plus, Trash2, Save } from "lucide-react";

type PermRow = { permission_code: string; can_read: boolean; can_write: boolean };

function PermissionMatrix({
  codes,
  initial,
  onSave,
}: {
  codes: string[];
  initial: PermRow[];
  onSave: (perms: PermRow[]) => Promise<void>;
}) {
  const [perms, setPerms] = useState<PermRow[]>(() =>
    codes.map((c) => {
      const found = initial.find((p) => p.permission_code === c);
      return found || { permission_code: c, can_read: false, can_write: false };
    })
  );
  const [saving, setSaving] = useState(false);

  function toggle(code: string, field: "can_read" | "can_write") {
    setPerms((prev) =>
      prev.map((p) => (p.permission_code === code ? { ...p, [field]: !p[field] } : p))
    );
  }

  async function save() {
    setSaving(true);
    try { await onSave(perms.filter((p) => p.can_read || p.can_write)); } finally { setSaving(false); }
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
              <th className="px-4 py-2">Permission</th>
              <th className="px-4 py-2 text-center">Read</th>
              <th className="px-4 py-2 text-center">Write</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {perms.map((p) => (
              <tr key={p.permission_code} className="hover:bg-slate-50/40">
                <td className="px-4 py-2 font-mono text-xs text-slate-600">{p.permission_code}</td>
                <td className="px-4 py-2 text-center">
                  <input type="checkbox" checked={p.can_read} onChange={() => toggle(p.permission_code, "can_read")} className="cursor-pointer" />
                </td>
                <td className="px-4 py-2 text-center">
                  <input type="checkbox" checked={p.can_write} onChange={() => toggle(p.permission_code, "can_write")} className="cursor-pointer" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex justify-end">
        <Button size="xs" icon={Save} loading={saving} onClick={save}>Save Permissions</Button>
      </div>
    </div>
  );
}

export default function RolePermissions() {
  const [roles, setRoles] = useState<any[]>([]);
  const [codes, setCodes] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [newRole, setNewRole] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [adding, setAdding] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [toast, setToast] = useState("");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  async function load() {
    const [r, c] = await Promise.all([adminListRoles(), adminListPermissionCodes()]);
    setRoles(r.data);
    setCodes(c.data);
  }

  useEffect(() => { load(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setAdding(true);
    try {
      await adminCreateRole({ role_name: newRole, description: newDesc });
      setNewRole(""); setNewDesc(""); setShowForm(false);
      flash("Role created");
      load();
    } finally { setAdding(false); }
  }

  async function handleDelete(name: string) {
    if (!confirm(`Delete role "${name}"?`)) return;
    await adminDeleteRole(name);
    flash("Deleted");
    load();
  }

  async function handleSavePerms(roleName: string, perms: PermRow[]) {
    await adminSetPermissions(roleName, perms);
    flash("Permissions saved");
    load();
  }

  return (
    <div className="space-y-6">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}

      <div className="flex items-center justify-between">
        <div><Title>Roles &amp; Permissions</Title><Text>Define roles and configure per-permission read/write access.</Text></div>
        <Button size="sm" icon={Plus} onClick={() => setShowForm(true)}>Add Role</Button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-slate-50 border rounded-lg p-4 flex gap-3 items-end flex-wrap">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Role Name *</label>
            <input required className="border rounded px-3 py-2 text-sm w-44 focus:outline-none focus:ring-2 focus:ring-blue-300" value={newRole} onChange={(e) => setNewRole(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Description</label>
            <input className="border rounded px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-300" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
          </div>
          <Button type="submit" size="xs" color="blue" loading={adding}>Create</Button>
          <Button type="button" size="xs" color="slate" variant="secondary" onClick={() => setShowForm(false)}>Cancel</Button>
        </form>
      )}

      <div className="space-y-3">
        {roles.map((role) => (
          <Card key={role.role_id} className="p-0 overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-slate-50/50 transition-colors"
              onClick={() => setExpanded(expanded === role.role_name ? null : role.role_name)}
            >
              <div>
                <span className="font-semibold text-slate-700">{role.role_name}</span>
                {role.description && <span className="ml-3 text-sm text-slate-400">{role.description}</span>}
                <span className="ml-3 text-xs text-slate-400">{(role.permissions || []).length} permissions</span>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(role.role_name); }}
                  className="text-slate-400 hover:text-rose-600"
                >
                  <Trash2 size={14} />
                </button>
                <span className="text-slate-300">{expanded === role.role_name ? "▲" : "▼"}</span>
              </div>
            </button>
            {expanded === role.role_name && (
              <div className="border-t px-5 py-4">
                <PermissionMatrix
                  codes={codes}
                  initial={role.permissions || []}
                  onSave={(perms) => handleSavePerms(role.role_name, perms)}
                />
              </div>
            )}
          </Card>
        ))}
        {roles.length === 0 && <div className="text-center py-12 text-gray-400 text-sm">No roles configured.</div>}
      </div>
    </div>
  );
}
