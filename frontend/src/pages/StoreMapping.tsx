import { useEffect, useMemo, useState } from "react";
import { adminListStores, adminUpdateStore, adminToggleStoreSync, adminUpdateStoreHours, onFlyListStores, onFlySync } from "../api/client";
import { Card, Title, Text, Badge } from "@tremor/react";
import { Pencil, X, Check, Play, Search, ChevronDown, Clock } from "lucide-react";

const EMPTY = { store_id: "", store_name: "", email: "", drive_folder_url: "" };

function StoreForm({ initial, onSave, onCancel, isNew }: {
  initial: typeof EMPTY; onSave: (v: typeof EMPTY) => Promise<void>; onCancel: () => void; isNew: boolean;
}) {
  const [v, setV] = useState(initial);
  const [saving, setSaving] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setSaving(true);
    try { await onSave(v); } finally { setSaving(false); }
  }
  return (
    <form onSubmit={submit} className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{isNew ? "New Store" : `Editing ${v.store_id}`}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="iris-label">Store ID *</label>
          <input className="iris-input" required disabled={!isNew} placeholder="e.g. BLRJAY" value={v.store_id} onChange={(e) => setV({ ...v, store_id: e.target.value })} />
        </div>
        <div>
          <label className="iris-label">Store Name *</label>
          <input className="iris-input" required placeholder="e.g. BLR - Jayanagar" value={v.store_name} onChange={(e) => setV({ ...v, store_name: e.target.value })} />
        </div>
        <div>
          <label className="iris-label">Email *</label>
          <input type="email" className="iris-input" required placeholder="store@example.com" value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} />
        </div>
        <div>
          <label className="iris-label">Drive Folder URL</label>
          <input className="iris-input" placeholder="https://drive.google.com/drive/folders/..." value={v.drive_folder_url} onChange={(e) => setV({ ...v, drive_folder_url: e.target.value })} />
        </div>
      </div>
      <div className="flex gap-2 pt-1 border-t border-slate-100">
        <button type="submit" disabled={saving} className="iris-btn-primary"><Check size={14} />{saving ? "Saving…" : "Save"}</button>
        <button type="button" onClick={onCancel} className="iris-btn-secondary"><X size={14} />Cancel</button>
      </div>
    </form>
  );
}

function toTimeStr(h: number, m: number) {
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function fromTimeStr(s: string): { h: number; m: number } {
  const [h, m] = s.split(":").map(Number);
  return { h: isNaN(h) ? 0 : h, m: isNaN(m) ? 0 : m };
}

function HoursEditor({ storeId, current, onSave, onCancel }: {
  storeId: string;
  current: { open_hour: number; open_minute: number; close_hour: number; close_minute: number };
  onSave: (oh: number, om: number, ch: number, cm: number) => Promise<void>;
  onCancel: () => void;
}) {
  const [openTime, setOpenTime] = useState(toTimeStr(current.open_hour, current.open_minute));
  const [closeTime, setCloseTime] = useState(toTimeStr(current.close_hour, current.close_minute));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const o = fromTimeStr(openTime);
    const c = fromTimeStr(closeTime);
    if (o.h * 60 + o.m >= c.h * 60 + c.m) { setErr("Open time must be before close time"); return; }
    setSaving(true); setErr("");
    try { await onSave(o.h, o.m, c.h, c.m); } catch (ex: any) {
      setErr(ex?.response?.data?.detail || "Save failed");
    } finally { setSaving(false); }
  }

  return (
    <form onSubmit={submit} className="bg-amber-50 border border-amber-200 rounded-xl p-4 shadow-sm">
      <p className="text-xs font-semibold text-amber-700 uppercase tracking-wider mb-3">
        <Clock size={12} className="inline mr-1" />Store Hours — {storeId}
      </p>
      <p className="text-[11px] text-amber-600 mb-3">
        Images outside these hours are skipped (no YOLO, no GPT). Default: 10:30 AM – 9:30 PM.
      </p>
      <div className="flex items-end gap-4 flex-wrap">
        <div>
          <label className="iris-label">Opens at</label>
          <input type="time" className="iris-input w-32" title="Store open time" value={openTime} onChange={(e) => setOpenTime(e.target.value)} />
        </div>
        <div>
          <label className="iris-label">Closes at</label>
          <input type="time" className="iris-input w-32" title="Store close time" value={closeTime} onChange={(e) => setCloseTime(e.target.value)} />
        </div>
        <div className="flex gap-2 pb-4">
          <button type="submit" disabled={saving} className="iris-btn-primary text-xs">
            <Check size={13} />{saving ? "Saving…" : "Save Hours"}
          </button>
          <button type="button" onClick={onCancel} className="iris-btn-secondary text-xs">
            <X size={13} />Cancel
          </button>
        </div>
      </div>
      {err && <p className="text-xs text-rose-500 mt-1">{err}</p>}
    </form>
  );
}

function HeaderFilter({ label, options, value, onChange }: {
  label: string; options: { value: string; label: string }[]; value: string; onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className={`flex items-center gap-1 text-xs font-semibold uppercase tracking-wider transition-colors ${value ? "text-blue-600" : "text-slate-500"}`}
      >
        {label} <ChevronDown size={11} className={value ? "text-blue-500" : "text-slate-400"} />
        {value && <span className="ml-1 h-1.5 w-1.5 rounded-full bg-blue-500 inline-block" />}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-[200] bg-white border border-slate-200 rounded-lg shadow-xl min-w-[140px] py-1">
          {options.map((o) => (
            <button
              type="button"
              key={o.value}
              onClick={() => { onChange(o.value); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-xs hover:bg-slate-50 ${o.value === value ? "text-blue-600 font-semibold bg-blue-50" : "text-slate-700"}`}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function StoreMapping() {
  const [rows, setRows] = useState<any[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [editingHours, setEditingHours] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const [syncData, setSyncData] = useState<Record<string, any>>({});
  const [syncing, setSyncing] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [driveFilter, setDriveFilter] = useState("");
  const [syncFilter, setSyncFilter] = useState("");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3500); }

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

  const filtered = useMemo(() => {
    let out = rows;
    const q = search.trim().toLowerCase();
    if (q) {
      out = out.filter((r) =>
        [r.store_id, r.store_name, r.email, r.drive_folder_url].some(
          (v) => String(v || "").toLowerCase().includes(q)
        )
      );
    }
    if (driveFilter === "set") out = out.filter((r) => Boolean(r.drive_folder_url));
    if (driveFilter === "notset") out = out.filter((r) => !r.drive_folder_url);
    if (syncFilter === "on") out = out.filter((r) => r.sync_enabled);
    if (syncFilter === "off") out = out.filter((r) => !r.sync_enabled);
    return out;
  }, [rows, search, driveFilter, syncFilter]);

  const activeFilters = [driveFilter, syncFilter].filter(Boolean).length + (search.trim() ? 1 : 0);

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
    } catch (e: any) { flash(e?.response?.data?.detail || "Toggle failed"); }
  }

  async function handleUpdate(v: typeof EMPTY) { await adminUpdateStore(v.store_id, v); setEditing(null); flash("Store updated"); load(); }

  async function handleHoursSave(storeId: string, oh: number, om: number, ch: number, cm: number) {
    await adminUpdateStoreHours(storeId, { open_hour: oh, open_minute: om, close_hour: ch, close_minute: cm });
    flash(`Hours updated: ${storeId} → ${toTimeStr(oh, om)} – ${toTimeStr(ch, cm)}`);
    setEditingHours(null);
    load();
  }

  function fmtHours(r: any) {
    const oh = r.open_hour ?? 10, om = r.open_minute ?? 30;
    const ch = r.close_hour ?? 21, cm = r.close_minute ?? 30;
    const fmt = (h: number, m: number) => {
      const ampm = h < 12 ? "AM" : "PM";
      const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
      return `${h12}:${String(m).padStart(2, "0")} ${ampm}`;
    };
    return `${fmt(oh, om)} – ${fmt(ch, cm)}`;
  }

  return (
    <div className="space-y-6">
      {toast && <div className="iris-toast">{toast}</div>}

      <div className="flex items-start justify-between gap-4">
        <div>
          <Title>Store Mapping</Title>
          <Text>Manage store registry, contact emails, and Drive folder links.</Text>
          <p className="mt-2 text-xs text-slate-400">
            Add or remove stores in <span className="font-semibold text-slate-500">Admin → Store Master</span>. This page is only for source mapping and auto-sync control.
          </p>
        </div>
      </div>

      <Card className="p-0 overflow-hidden">
        {/* Search bar */}
        <div className="px-4 py-3 border-b flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[220px] max-w-sm">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="iris-input pl-8"
              placeholder="Search store ID, name, email, URL…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {activeFilters > 0 && (
            <button
              type="button"
              onClick={() => { setSearch(""); setDriveFilter(""); setSyncFilter(""); }}
              className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              <X size={12} /> Clear {activeFilters} filter{activeFilters > 1 ? "s" : ""}
            </button>
          )}
          <span className="text-xs text-slate-400 ml-auto">{filtered.length} / {rows.length} stores</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="bg-slate-50 border-b">
                <th className="px-4 py-3 text-slate-500 text-xs uppercase tracking-wider font-semibold w-10">#</th>
                <th className="px-5 py-3 text-slate-500 text-xs uppercase tracking-wider font-semibold">Store ID</th>
                <th className="px-5 py-3 text-slate-500 text-xs uppercase tracking-wider font-semibold">Name</th>
                <th className="px-5 py-3">
                  <HeaderFilter
                    label="Drive Link"
                    value={driveFilter}
                    onChange={setDriveFilter}
                    options={[
                      { value: "", label: "All" },
                      { value: "set", label: "Has URL ✓" },
                      { value: "notset", label: "No URL ✗" },
                    ]}
                  />
                </th>
                <th className="px-5 py-3 text-slate-500 text-xs uppercase tracking-wider font-semibold">Store Hours</th>
                <th className="px-5 py-3 text-slate-500 text-xs uppercase tracking-wider font-semibold">Last Sync</th>
                <th className="px-5 py-3">
                  <HeaderFilter
                    label="Auto Sync"
                    value={syncFilter}
                    onChange={setSyncFilter}
                    options={[
                      { value: "", label: "All" },
                      { value: "on", label: "Enabled" },
                      { value: "off", label: "Disabled" },
                    ]}
                  />
                </th>
                <th className="px-5 py-3 text-slate-500 text-xs uppercase tracking-wider font-semibold sticky right-0 bg-slate-50 shadow-[-8px_0_8px_-4px_rgba(0,0,0,0.05)]">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((r, idx) => {
                const sync = syncData[r.store_id];
                return (
                  <>
                    <tr key={r.store_id} className="hover:bg-slate-50/50">
                      <td className="px-4 py-3 text-slate-400 text-xs text-center">{idx + 1}</td>
                      <td className="px-5 py-3 font-medium font-mono text-xs">{r.store_id}</td>
                      <td className="px-5 py-3 font-medium">{r.store_name}</td>
                      <td className="px-5 py-3 max-w-[160px] truncate text-slate-400 text-xs">
                        {r.drive_folder_url ? (
                          <a href={r.drive_folder_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                            {r.drive_folder_url}
                          </a>
                        ) : <span className="text-rose-400">Not set</span>}
                      </td>
                      <td className="px-5 py-3">
                        <span className="text-xs text-slate-600 font-mono">{fmtHours(r)}</span>
                      </td>
                      <td className="px-5 py-3">
                        {sync ? (
                          <div className="space-y-0.5">
                            <Badge color={sync.is_running ? "amber" : sync.last_status === "ok" ? "emerald" : sync.last_status === "error" ? "rose" : "slate"}>
                              {sync.is_running ? `running${sync.current_stage ? ` • ${String(sync.current_stage).toLowerCase()}` : ""}` : sync.last_status || "never"}
                            </Badge>
                            {sync.last_sync_at && <p className="text-xs text-slate-400">{new Date(sync.last_sync_at).toLocaleDateString("en-IN")}</p>}
                            {sync.last_message ? (
                              <p className={`max-w-[220px] truncate text-[10px] ${sync.last_status === "error" && !sync.is_running ? "text-rose-500" : "text-slate-400"}`} title={sync.last_message}>
                                {sync.last_message}
                              </p>
                            ) : null}
                          </div>
                        ) : <span className="text-slate-400 text-xs">Never</span>}
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex flex-col items-start gap-1">
                          <button
                            type="button"
                            onClick={() => handleToggleSync(r.store_id, !r.sync_enabled, r.sync_interval_hours || 1)}
                            disabled={!r.drive_folder_url}
                            title={r.sync_enabled ? "Auto-sync ON — click to disable" : "Auto-sync OFF — click to enable"}
                            className={`relative inline-flex h-5 w-10 shrink-0 items-center rounded-full transition-colors focus:outline-none disabled:opacity-30 ${r.sync_enabled ? "bg-emerald-500" : "bg-slate-200"}`}
                          >
                            <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${r.sync_enabled ? "translate-x-5" : "translate-x-0.5"}`} />
                          </button>
                          <span className={`text-[10px] font-medium ${r.sync_enabled ? "text-emerald-600" : "text-slate-400"}`}>
                            {r.sync_enabled ? `Enabled • Every ${r.sync_interval_hours || 1}h` : "Disabled"}
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-3 sticky right-0 bg-white shadow-[-8px_0_8px_-4px_rgba(0,0,0,0.05)]">
                        <div className="flex gap-2 items-center">
                          <button type="button" onClick={() => handleSync(r.store_id)} disabled={syncing === r.store_id || !r.drive_folder_url} className="text-slate-400 hover:text-emerald-600 disabled:opacity-30" title="Sync now"><Play size={14} /></button>
                          <button
                            type="button"
                            onClick={() => { setEditingHours(editingHours === r.store_id ? null : r.store_id); setEditing(null); }}
                            className={`${editingHours === r.store_id ? "text-amber-600" : "text-slate-400 hover:text-amber-600"}`}
                            title="Set store hours"
                          >
                            <Clock size={14} />
                          </button>
                          <button type="button" onClick={() => { setEditing(editing === r.store_id ? null : r.store_id); setEditingHours(null); }} className="text-slate-400 hover:text-blue-600" title="Edit"><Pencil size={14} /></button>
                        </div>
                      </td>
                    </tr>
                    {editingHours === r.store_id && (
                      <tr key={`hours-${r.store_id}`}>
                        <td colSpan={8} className="px-5 py-3">
                          <HoursEditor
                            storeId={r.store_id}
                            current={{ open_hour: r.open_hour ?? 10, open_minute: r.open_minute ?? 30, close_hour: r.close_hour ?? 21, close_minute: r.close_minute ?? 30 }}
                            onSave={(oh, om, ch, cm) => handleHoursSave(r.store_id, oh, om, ch, cm)}
                            onCancel={() => setEditingHours(null)}
                          />
                        </td>
                      </tr>
                    )}
                    {editing === r.store_id && (
                      <tr key={`edit-${r.store_id}`}>
                        <td colSpan={8} className="px-5 py-3">
                          <StoreForm initial={r} onSave={handleUpdate} onCancel={() => setEditing(null)} isNew={false} />
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center py-12 text-gray-400 text-sm">
                    {rows.length === 0 ? "No stores configured." : "No stores match the current filters."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
