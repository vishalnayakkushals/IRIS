import { useEffect, useState } from "react";
import {
  adminListUsers,
  adminListStores,
  adminGetStoreAccess,
  adminReplaceStoreAccess,
} from "../api/client";
import { Card, Title, Text, Button, Badge } from "@tremor/react";
import { Save } from "lucide-react";

export default function StoreAccess() {
  const [users, setUsers] = useState<any[]>([]);
  const [stores, setStores] = useState<any[]>([]);
  const [selectedEmail, setSelectedEmail] = useState("");
  const [access, setAccess] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  useEffect(() => {
    Promise.all([adminListUsers(), adminListStores()]).then(([u, s]) => {
      setUsers(u.data);
      setStores(s.data);
    });
  }, []);

  useEffect(() => {
    if (!selectedEmail) { setAccess([]); return; }
    adminGetStoreAccess(selectedEmail).then((r) => {
      setAccess(r.data.map((row: any) => row.store_id));
    });
  }, [selectedEmail]);

  function toggle(storeId: string) {
    setAccess((prev) =>
      prev.includes(storeId) ? prev.filter((s) => s !== storeId) : [...prev, storeId]
    );
  }

  async function save() {
    if (!selectedEmail) return;
    setSaving(true);
    try {
      await adminReplaceStoreAccess(selectedEmail, access);
      flash("Access saved");
    } finally { setSaving(false); }
  }

  const selectedUser = users.find((u) => u.email === selectedEmail);

  return (
    <div className="space-y-6">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}

      <div>
        <Title>Store Access Mapping</Title>
        <Text>Control which stores each user can access in reports and dashboards.</Text>
      </div>

      <Card className="p-5 space-y-5">
        <div>
          <label className="block text-xs text-slate-500 mb-2">Select User</label>
          <select
            className="border rounded px-3 py-2 text-sm w-72 focus:outline-none focus:ring-2 focus:ring-blue-300"
            value={selectedEmail}
            onChange={(e) => setSelectedEmail(e.target.value)}
          >
            <option value="">— choose a user —</option>
            {users.map((u) => (
              <option key={u.email} value={u.email}>{u.full_name} ({u.email})</option>
            ))}
          </select>
        </div>

        {selectedUser && (
          <div className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
            <div>
              <p className="font-semibold text-slate-700 text-sm">{selectedUser.full_name}</p>
              <p className="text-xs text-slate-400">{selectedUser.email}</p>
            </div>
            <div className="flex gap-1 flex-wrap">
              {(selectedUser.roles || []).map((r: string) => <Badge key={r} color="blue">{r}</Badge>)}
            </div>
          </div>
        )}

        {selectedEmail && (
          <>
            <div>
              <p className="text-xs text-slate-500 mb-3 uppercase tracking-wide font-semibold">Store Access</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {stores.map((s) => {
                  const checked = access.includes(s.store_id);
                  return (
                    <button
                      key={s.store_id}
                      type="button"
                      onClick={() => toggle(s.store_id)}
                      className={`border rounded-lg px-3 py-2.5 text-left transition-colors ${checked ? "bg-blue-600 text-white border-blue-600" : "bg-white hover:border-blue-300 text-slate-700"}`}
                    >
                      <p className="font-medium text-sm">{s.store_name}</p>
                      <p className={`text-xs mt-0.5 ${checked ? "text-blue-100" : "text-slate-400"}`}>{s.store_id}</p>
                    </button>
                  );
                })}
                {stores.length === 0 && <p className="text-slate-400 text-sm">No stores available.</p>}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button color="blue" icon={Save} loading={saving} onClick={save}>Save Access</Button>
              <span className="text-sm text-slate-400">{access.length} store(s) selected</span>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
