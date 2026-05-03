import { useEffect, useState } from "react";
import {
  adminListUsers,
  adminListStores,
  adminListStoreMaster,
  adminGetStoreAccess,
  adminReplaceStoreAccess,
} from "../api/client";
import { Title, Text, Button, Badge } from "@tremor/react";
import { Save, ChevronRight, ChevronLeft } from "lucide-react";

interface StoreWithMeta {
  store_id: string;
  store_name: string;
  city: string;
  state: string;
  zone: string;
}

export default function StoreAccess() {
  const [users, setUsers] = useState<any[]>([]);
  const [allStores, setAllStores] = useState<StoreWithMeta[]>([]);
  const [selectedEmail, setSelectedEmail] = useState("");
  const [granted, setGranted] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");

  const [stateFilter, setStateFilter] = useState("");
  const [zoneFilter, setZoneFilter] = useState("");
  const [leftSearch, setLeftSearch] = useState("");
  const [rightSearch, setRightSearch] = useState("");
  const [leftSelected, setLeftSelected] = useState<string[]>([]);
  const [rightSelected, setRightSelected] = useState<string[]>([]);

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3500); }

  useEffect(() => {
    Promise.all([adminListUsers(), adminListStores(), adminListStoreMaster()]).then(([u, s, sm]) => {
      setUsers(u.data);
      const masterMap: Record<string, any> = {};
      (sm.data || []).forEach((m: any) => { masterMap[m.store_id] = m; });
      setAllStores((s.data || []).map((store: any) => ({
        store_id: store.store_id,
        store_name: store.store_name || store.store_id,
        city: masterMap[store.store_id]?.city || "",
        state: masterMap[store.store_id]?.state || "",
        zone: masterMap[store.store_id]?.zone || "",
      })));
    });
  }, []);

  useEffect(() => {
    if (!selectedEmail) { setGranted([]); setLeftSelected([]); setRightSelected([]); return; }
    adminGetStoreAccess(selectedEmail).then((r) => {
      setGranted((r.data || []).map((row: any) => row.store_id));
    });
    setLeftSelected([]);
    setRightSelected([]);
  }, [selectedEmail]);

  const grantedSet = new Set(granted);
  const available = allStores.filter((s) => !grantedSet.has(s.store_id));
  const grantedStores = allStores.filter((s) => grantedSet.has(s.store_id));

  const states = [...new Set(allStores.map((s) => s.state).filter(Boolean))].sort();
  const zones = [...new Set(
    allStores.filter((s) => !stateFilter || s.state === stateFilter).map((s) => s.zone).filter(Boolean)
  )].sort();

  const filteredAvailable = available.filter((s) => {
    if (stateFilter && s.state !== stateFilter) return false;
    if (zoneFilter && s.zone !== zoneFilter) return false;
    if (leftSearch && !`${s.store_id} ${s.store_name}`.toLowerCase().includes(leftSearch.toLowerCase())) return false;
    return true;
  });

  const filteredGranted = grantedStores.filter((s) =>
    !rightSearch || `${s.store_id} ${s.store_name}`.toLowerCase().includes(rightSearch.toLowerCase())
  );

  function addSelected() {
    const ids = leftSelected.length > 0 ? leftSelected : filteredAvailable.map((s) => s.store_id);
    setGranted((prev) => [...new Set([...prev, ...ids])]);
    setLeftSelected([]);
  }

  function removeSelected() {
    const ids = rightSelected.length > 0 ? rightSelected : filteredGranted.map((s) => s.store_id);
    setGranted((prev) => prev.filter((id) => !ids.includes(id)));
    setRightSelected([]);
  }

  function toggleLeft(id: string) {
    setLeftSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  function toggleRight(id: string) {
    setRightSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  const allGranted = allStores.length > 0 && granted.length === allStores.length;

  async function save() {
    if (!selectedEmail) return;
    setSaving(true);
    try {
      await adminReplaceStoreAccess(selectedEmail, granted);
      flash(`Access saved — ${granted.length} store(s) granted to ${selectedEmail}`);
    } catch { flash("Save failed"); } finally { setSaving(false); }
  }

  const selectedUser = users.find((u) => u.email === selectedEmail);

  return (
    <div className="space-y-6">
      {toast && <div className="iris-toast">{toast}</div>}

      <div>
        <Title>Store Access Mapping</Title>
        <Text>Control which stores each user can access in reports and dashboards.</Text>
      </div>

      {/* User selector */}
      <div className="flex flex-wrap gap-4 items-end">
        <div>
          <label className="iris-label">Select User</label>
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
          <div className="flex items-center gap-2 p-2.5 bg-slate-50 border rounded-lg">
            <p className="text-sm font-semibold text-slate-700">{selectedUser.full_name}</p>
            <p className="text-xs text-slate-400">{selectedUser.email}</p>
            {(selectedUser.roles || []).map((r: string) => <Badge key={r} color="blue">{r}</Badge>)}
          </div>
        )}
      </div>

      {selectedEmail && (
        <>
          {/* All Stores quick-grant */}
          <div className="flex items-center justify-between p-4 border rounded-xl bg-slate-50">
            <div>
              <p className="text-sm font-semibold text-slate-700">Grant All Stores Access</p>
              <p className="text-xs text-slate-400 mt-0.5">
                Instantly grant access to all {allStores.length} stores in the system.
              </p>
            </div>
            <button
              type="button"
              onClick={() => allGranted ? setGranted([]) : setGranted(allStores.map((s) => s.store_id))}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                allGranted
                  ? "bg-blue-600 text-white hover:bg-blue-700"
                  : "bg-white border border-blue-300 text-blue-600 hover:bg-blue-50"
              }`}
            >
              {allGranted ? "✓ All Stores Granted — Click to Clear" : "Grant All Stores"}
            </button>
          </div>

          {/* Filters for left panel */}
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="iris-label">Filter by State</label>
              <select
                className="border rounded px-2 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-300"
                value={stateFilter}
                onChange={(e) => { setStateFilter(e.target.value); setZoneFilter(""); setLeftSelected([]); }}
              >
                <option value="">All States</option>
                {states.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="iris-label">Filter by Zone</label>
              <select
                className="border rounded px-2 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-300"
                value={zoneFilter}
                onChange={(e) => { setZoneFilter(e.target.value); setLeftSelected([]); }}
              >
                <option value="">All Zones</option>
                {zones.map((z) => <option key={z} value={z}>{z}</option>)}
              </select>
            </div>
            {(stateFilter || zoneFilter) && (
              <button
                type="button"
                onClick={() => { setStateFilter(""); setZoneFilter(""); setLeftSelected([]); }}
                className="text-xs text-slate-400 hover:text-slate-600 pb-1"
              >
                Clear filters
              </button>
            )}
            {stateFilter && (
              <button
                type="button"
                onClick={() => addSelected()}
                className="text-xs px-3 py-1.5 bg-blue-50 text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors pb-1"
              >
                Add all {stateFilter} stores ({filteredAvailable.length})
              </button>
            )}
          </div>

          {/* Dual listbox */}
          <div className="grid grid-cols-[1fr_52px_1fr] gap-3 items-center">
            {/* Left: Available */}
            <div className="border rounded-xl overflow-hidden">
              <div className="bg-slate-50 px-3 py-2 border-b flex items-center justify-between">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Available ({filteredAvailable.length})
                </p>
                <div className="flex gap-2">
                  {leftSelected.length > 0 && (
                    <span className="text-xs text-blue-500">{leftSelected.length} selected</span>
                  )}
                  {filteredAvailable.length > 0 && (
                    <button
                      onClick={() => setLeftSelected(
                        leftSelected.length === filteredAvailable.length
                          ? []
                          : filteredAvailable.map((s) => s.store_id)
                      )}
                      className="text-xs text-blue-500 hover:text-blue-700"
                    >
                      {leftSelected.length === filteredAvailable.length ? "Deselect all" : "Select all"}
                    </button>
                  )}
                </div>
              </div>
              <div className="p-2 border-b">
                <input
                  className="w-full border rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300"
                  placeholder="Search stores…"
                  value={leftSearch}
                  onChange={(e) => { setLeftSearch(e.target.value); setLeftSelected([]); }}
                />
              </div>
              <div className="h-72 overflow-y-auto">
                {filteredAvailable.length === 0 ? (
                  <p className="text-xs text-slate-400 text-center py-10">
                    {available.length === 0 ? "All stores granted" : "No matches for current filters"}
                  </p>
                ) : (
                  filteredAvailable.map((s) => {
                    const isSelected = leftSelected.includes(s.store_id);
                    return (
                      <button
                        key={s.store_id}
                        onClick={() => toggleLeft(s.store_id)}
                        onDoubleClick={() => { setGranted((prev) => [...new Set([...prev, s.store_id])]); }}
                        className={`w-full text-left px-3 py-2 border-b border-slate-50 transition-colors ${
                          isSelected ? "bg-blue-50 border-l-2 border-l-blue-500" : "hover:bg-slate-50"
                        }`}
                      >
                        <p className="text-xs font-medium text-slate-700">{s.store_name}</p>
                        <p className="text-[10px] text-slate-400 font-mono">
                          {s.store_id}
                          {s.state ? ` · ${s.state}` : ""}
                          {s.zone ? ` · ${s.zone}` : ""}
                        </p>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Arrow buttons */}
            <div className="flex flex-col gap-2 items-center">
              <button
                onClick={addSelected}
                disabled={filteredAvailable.length === 0}
                className="p-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors"
                title={leftSelected.length > 0 ? `Add ${leftSelected.length} selected` : "Add all filtered"}
              >
                <ChevronRight size={16} />
              </button>
              <button
                onClick={removeSelected}
                disabled={filteredGranted.length === 0}
                className="p-2.5 bg-slate-200 text-slate-600 rounded-lg hover:bg-slate-300 disabled:opacity-40 transition-colors"
                title={rightSelected.length > 0 ? `Remove ${rightSelected.length} selected` : "Remove all filtered"}
              >
                <ChevronLeft size={16} />
              </button>
            </div>

            {/* Right: Granted */}
            <div className="border rounded-xl overflow-hidden">
              <div className="bg-emerald-50 px-3 py-2 border-b flex items-center justify-between">
                <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">
                  Granted Access ({granted.length}{allGranted ? " — All Stores" : ""})
                </p>
                {rightSelected.length > 0 && (
                  <span className="text-xs text-rose-500">{rightSelected.length} selected</span>
                )}
              </div>
              <div className="p-2 border-b">
                <input
                  className="w-full border rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300"
                  placeholder="Search granted…"
                  value={rightSearch}
                  onChange={(e) => { setRightSearch(e.target.value); setRightSelected([]); }}
                />
              </div>
              <div className="h-72 overflow-y-auto">
                {filteredGranted.length === 0 ? (
                  <p className="text-xs text-slate-400 text-center py-10">No stores granted yet</p>
                ) : (
                  filteredGranted.map((s) => {
                    const isSelected = rightSelected.includes(s.store_id);
                    return (
                      <button
                        key={s.store_id}
                        onClick={() => toggleRight(s.store_id)}
                        onDoubleClick={() => setGranted((prev) => prev.filter((id) => id !== s.store_id))}
                        className={`w-full text-left px-3 py-2 border-b border-slate-50 transition-colors ${
                          isSelected ? "bg-rose-50 border-l-2 border-l-rose-400" : "hover:bg-emerald-50/50"
                        }`}
                      >
                        <p className="text-xs font-medium text-slate-700">{s.store_name}</p>
                        <p className="text-[10px] text-slate-400 font-mono">
                          {s.store_id}
                          {s.state ? ` · ${s.state}` : ""}
                        </p>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          <p className="text-xs text-slate-400">Tip: Click to select, double-click to move instantly. Arrow moves selection or all filtered stores.</p>

          <div className="flex items-center gap-3">
            <Button color="blue" icon={Save} loading={saving} onClick={save}>Save Access</Button>
            <span className="text-sm text-slate-500">{granted.length} of {allStores.length} stores granted</span>
            {granted.length > 0 && (
              <button onClick={() => setGranted([])} className="text-xs text-rose-400 hover:text-rose-600">
                Clear all
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
