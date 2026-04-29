import { useEffect, useState } from "react";
import { adminListStores, adminCreateStore, adminUpdateStore, adminDeleteStore, adminToggleStoreSync, onFlyListStores, onFlySync } from "../api/client";
import { Card, Title, Text, Badge } from "@tremor/react";
import { Plus, Pencil, Trash2, X, Check, Play } from "lucide-react";

const EMPTY = { store_id: "", store_name: "", email: "", drive_folder_url: "" };

function StoreForm({
  initial,
  onSave,
  onCancel,
  isNew,
}: {
  initial: typeof EMPTY;
  onSave: (v: typeof EMPTY) => Promise<void>;
  onCancel: () => void;
  isNew: boolean;
}) {
  const [v, setV] = useState(initial);
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try { await onSave(v); } finally { setSaving(false); }
  }

  return (
    <form onSubmit={submit} className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
        {isNew ? "New Store" : `Editing ${v.store_id}`}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1.5">Store ID *</label>
          <input
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-slate-50 disabled:text-slate-400"
            required
            disabled={!isNew}
            placeholder="e.g. BLRJAY"
            value={v.store_id}
            onChange={(e) => setV({ ...v, store_id: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1.5">Store Name *</label>
          <input
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            required
            placeholder="e.g. BLR - Jayanagar"
            value={v.store_name}
            onChange={(e) => setV({ ...v, store_name: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1.5">Email *</label>
          <input
            type="email"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            required
            placeholder="store@example.com"
            value={v.email}
            onChange={(e) => setV({ ...v, email: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1.5">Drive Folder URL</label>
          <input
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="https://drive.google.com/drive/folders/..."
            value={v.drive_folder_url}
            onChange={(e) => setV({ ...v, drive_folder_url: e.target.value })}
          />
        </div>
      </div>
      <div className="flex gap-2 pt-1 border-t border-slate-100">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Check size={14} />
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 text-sm font-medium rounded-lg transition-colors"
        >
          <X size={14} />
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function StoreMapping() {
  const [rows, setRows] = useState<any[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [toast, setToast] = useState("");

  function flash(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3500);
  }

  const [syncData, setSyncData] = useState<Record<string, any>>({});
  const [syncing, setSyncing] = useState<string | null>(null);

  async function load() {
    const [adminR, syncR] = await Promise.all([
      adminListStores(),
      onFlyListStores().catch(() => ({ data: [] })),
    ]);
    setRows(adminR.data);
    const byId: Record<string, any> = {};
    for (const s of (syncR as any).data) byId[s.store_id] = s;
    setSyncData(byId);
  }

  useEffect(() => { load(); }, []);

  async function handleSync(storeId: string) {
    setSyncing(storeId);
    try {
      const { data } = await onFlySync(storeId, { gpt_enabled: false });
      flash(data.message || "Sync started");
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Sync failed");
    } finally { setSyncing(null); }
  }

  async function handleToggleSync(storeId: string, enable: boolean, intervalHours = 1) {
    try {
      await adminToggleStoreSync(storeId, { sync_enabled: enable, sync_interval_hours: intervalHours });
      flash(enable ? `Auto-sync enabled for ${storeId}` : `Auto-sync disabled for ${storeId}`);
      load();
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Toggle failed");
    }
  }

  async function handleCreate(v: typeof EMPTY) {
    await adminCreateStore(v);
    setShowNew(false);
    flash("Store created");
    load();
  }

  async function handleUpdate(v: typeof EMPTY) {
    await adminUpdateStore(v.store_id, v);
    setEditing(null);
    flash("Store updated");
    load();
  }

  async function handleDelete(id: string) {
    if (!confirm(`Delete store ${id}? This cannot be undone.`)) return;
    await adminDeleteStore(id);
    flash("Store deleted");
    load();
  }

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">
          {toast}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <Title>Store Mapping</Title>
          <Text>Manage store registry, contact emails, and Drive folder links.</Text>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors shadow-sm"
        >
          <Plus size={15} /> Add Store
        </button>
      </div>

      {showNew && (
        <StoreForm initial={EMPTY} onSave={handleCreate} onCancel={() => setShowNew(false)} isNew />
      )}

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
              <th className="px-5 py-3">Store ID</th>
              <th className="px-5 py-3">Name</th>
              <th className="px-5 py-3">Email</th>
              <th className="px-5 py-3">Drive Link</th>
              <th className="px-5 py-3">Last Sync</th>
              <th className="px-5 py-3">Auto Sync</th>
              <th className="px-5 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => {
              const sync = syncData[r.store_id];
              return (
              <>
                <tr key={r.store_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3 font-medium font-mono text-xs">{r.store_id}</td>
                  <td className="px-5 py-3 font-medium">{r.store_name}</td>
                  <td className="px-5 py-3 text-slate-500">{r.email}</td>
                  <td className="px-5 py-3 max-w-[180px] truncate text-slate-400 text-xs">
                    {r.drive_folder_url ? (
                      <a href={r.drive_folder_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                        {r.drive_folder_url}
                      </a>
                    ) : <span className="text-rose-400">Not set</span>}
                  </td>
                  <td className="px-5 py-3">
                    {sync ? (
                      <div className="space-y-0.5">
                        <Badge color={sync.last_status === "ok" ? "emerald" : sync.last_status === "error" ? "rose" : "slate"}>
                          {sync.last_status || "never"}
                        </Badge>
                        {sync.last_sync_at && <p className="text-xs text-slate-400">{new Date(sync.last_sync_at).toLocaleDateString("en-IN")}</p>}
                      </div>
                    ) : <span className="text-slate-400 text-xs">Never</span>}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex flex-col items-start gap-1">
                      <button
                        onClick={() => handleToggleSync(r.store_id, !r.sync_enabled, r.sync_interval_hours || 1)}
                        disabled={!r.drive_folder_url}
                        title={r.sync_enabled ? "Auto-sync ON — click to disable" : "Auto-sync OFF — click to enable"}
                        className={`relative inline-flex h-5 w-10 shrink-0 items-center rounded-full transition-colors focus:outline-none disabled:opacity-30 ${r.sync_enabled ? "bg-emerald-500" : "bg-slate-200"}`}
                      >
                        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${r.sync_enabled ? "translate-x-5" : "translate-x-0.5"}`} />
                      </button>
                      {r.sync_enabled && (
                        <span className="text-[10px] text-emerald-600 font-medium">Every {r.sync_interval_hours || 1}h</span>
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex gap-2 items-center">
                      <button
                        onClick={() => handleSync(r.store_id)}
                        disabled={syncing === r.store_id || !r.drive_folder_url}
                        className="text-slate-400 hover:text-emerald-600 disabled:opacity-30"
                        title="Sync now"
                      >
                        <Play size={14} />
                      </button>
                      <button onClick={() => setEditing(editing === r.store_id ? null : r.store_id)} className="text-slate-400 hover:text-blue-600">
                        <Pencil size={15} />
                      </button>
                      <button onClick={() => handleDelete(r.store_id)} className="text-slate-400 hover:text-rose-600">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
                {editing === r.store_id && (
                  <tr key={`edit-${r.store_id}`}>
                    <td colSpan={7} className="px-5 py-3">
                      <StoreForm
                        initial={r}
                        onSave={handleUpdate}
                        onCancel={() => setEditing(null)}
                        isNew={false}
                      />
                    </td>
                  </tr>
                )}
              </>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center py-12 text-gray-400 text-sm">No stores configured.</td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
