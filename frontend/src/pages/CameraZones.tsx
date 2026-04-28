import { useEffect, useState } from "react";
import {
  adminListStores,
  adminListCameras,
  adminUpsertCamera,
  adminDeleteCamera,
  adminListLocations,
  adminUpsertLocation,
  adminDeleteLocation,
} from "../api/client";
import { Card, Title, Text, Button, Select, SelectItem, TabGroup, TabList, Tab, TabPanels, TabPanel } from "@tremor/react";
import { Plus, Trash2, Check, X } from "lucide-react";

const CAM_ROLES = ["INSIDE", "ENTRY", "EXIT", "OUTSIDE"];
const DIRECTIONS = ["OUTSIDE_TO_INSIDE", "INSIDE_TO_OUTSIDE"];

function CameraForm({ storeId, onSave, onCancel }: { storeId: string; onSave: () => void; onCancel: () => void }) {
  const [v, setV] = useState({ camera_id: "", camera_role: "INSIDE", floor_name: "", location_name: "", entry_line_x: 0.5, entry_direction: "OUTSIDE_TO_INSIDE" });
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try { await adminUpsertCamera(storeId, v); onSave(); } finally { setSaving(false); }
  }

  return (
    <form onSubmit={submit} className="bg-slate-50 border rounded-lg p-4 space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Camera ID *</label>
          <input className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" required value={v.camera_id} onChange={(e) => setV({ ...v, camera_id: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Role</label>
          <select className="w-full border rounded px-2 py-1.5 text-sm" value={v.camera_role} onChange={(e) => setV({ ...v, camera_role: e.target.value })}>
            {CAM_ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Entry Direction</label>
          <select className="w-full border rounded px-2 py-1.5 text-sm" value={v.entry_direction} onChange={(e) => setV({ ...v, entry_direction: e.target.value })}>
            {DIRECTIONS.map((d) => <option key={d}>{d}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Floor</label>
          <input className="w-full border rounded px-2 py-1.5 text-sm" value={v.floor_name} onChange={(e) => setV({ ...v, floor_name: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Location</label>
          <input className="w-full border rounded px-2 py-1.5 text-sm" value={v.location_name} onChange={(e) => setV({ ...v, location_name: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Entry Line X (0–1)</label>
          <input type="number" min={0} max={1} step={0.01} className="w-full border rounded px-2 py-1.5 text-sm" value={v.entry_line_x} onChange={(e) => setV({ ...v, entry_line_x: parseFloat(e.target.value) })} />
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="xs" color="blue" loading={saving} icon={Check}>Save</Button>
        <Button type="button" size="xs" color="slate" variant="secondary" onClick={onCancel} icon={X}>Cancel</Button>
      </div>
    </form>
  );
}

function LocationForm({ storeId, onSave, onCancel }: { storeId: string; onSave: () => void; onCancel: () => void }) {
  const [v, setV] = useState({ floor_name: "Ground", location_name: "" });
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try { await adminUpsertLocation(storeId, v); onSave(); } finally { setSaving(false); }
  }

  return (
    <form onSubmit={submit} className="bg-slate-50 border rounded-lg p-4 flex gap-3 items-end">
      <div>
        <label className="block text-xs text-slate-500 mb-1">Floor</label>
        <input className="border rounded px-2 py-1.5 text-sm w-32" value={v.floor_name} onChange={(e) => setV({ ...v, floor_name: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs text-slate-500 mb-1">Location Name *</label>
        <input className="border rounded px-2 py-1.5 text-sm w-48" required value={v.location_name} onChange={(e) => setV({ ...v, location_name: e.target.value })} />
      </div>
      <Button type="submit" size="xs" color="blue" loading={saving} icon={Check}>Save</Button>
      <Button type="button" size="xs" color="slate" variant="secondary" onClick={onCancel} icon={X}>Cancel</Button>
    </form>
  );
}

export default function CameraZones() {
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState("");
  const [cameras, setCameras] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [showCamForm, setShowCamForm] = useState(false);
  const [showLocForm, setShowLocForm] = useState(false);
  const [toast, setToast] = useState("");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  useEffect(() => { adminListStores().then((r) => { setStores(r.data); if (r.data.length) setStoreId(r.data[0].store_id); }); }, []);

  useEffect(() => {
    if (!storeId) return;
    adminListCameras(storeId).then((r) => setCameras(r.data));
    adminListLocations(storeId).then((r) => setLocations(r.data));
  }, [storeId]);

  async function delCamera(cid: string) {
    if (!confirm(`Delete camera ${cid}?`)) return;
    await adminDeleteCamera(storeId, cid);
    flash("Deleted");
    adminListCameras(storeId).then((r) => setCameras(r.data));
  }

  async function delLocation(floor: string, loc: string) {
    if (!confirm(`Delete ${floor} / ${loc}?`)) return;
    await adminDeleteLocation(storeId, floor, loc);
    flash("Deleted");
    adminListLocations(storeId).then((r) => setLocations(r.data));
  }

  return (
    <div className="space-y-6">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}

      <div className="flex items-center justify-between">
        <div><Title>Camera Zones</Title><Text>Configure cameras and store location master.</Text></div>
        <div className="w-52">
          <Select value={storeId} onValueChange={setStoreId} placeholder="Select store">
            {stores.map((s) => <SelectItem key={s.store_id} value={s.store_id}>{s.store_name}</SelectItem>)}
          </Select>
        </div>
      </div>

      <TabGroup>
        <TabList><Tab>Cameras</Tab><Tab>Locations</Tab></TabList>
        <TabPanels>
          <TabPanel>
            <div className="mt-4 space-y-3">
              <Button size="sm" icon={Plus} onClick={() => setShowCamForm(true)}>Add Camera</Button>
              {showCamForm && <CameraForm storeId={storeId} onSave={() => { setShowCamForm(false); adminListCameras(storeId).then((r) => setCameras(r.data)); flash("Saved"); }} onCancel={() => setShowCamForm(false)} />}
              <Card className="p-0 overflow-hidden">
                <table className="w-full text-sm text-left">
                  <thead>
                    <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
                      <th className="px-5 py-3">Camera ID</th>
                      <th className="px-5 py-3">Role</th>
                      <th className="px-5 py-3">Floor</th>
                      <th className="px-5 py-3">Location</th>
                      <th className="px-5 py-3">Entry X</th>
                      <th className="px-5 py-3">Direction</th>
                      <th className="px-5 py-3"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {cameras.map((c) => (
                      <tr key={c.camera_id} className="hover:bg-slate-50/50">
                        <td className="px-5 py-3 font-mono text-xs">{c.camera_id}</td>
                        <td className="px-5 py-3">{c.camera_role}</td>
                        <td className="px-5 py-3">{c.floor_name || "—"}</td>
                        <td className="px-5 py-3">{c.location_name || "—"}</td>
                        <td className="px-5 py-3">{c.entry_line_x}</td>
                        <td className="px-5 py-3 text-xs text-slate-500">{c.entry_direction}</td>
                        <td className="px-5 py-3"><button onClick={() => delCamera(c.camera_id)} className="text-slate-400 hover:text-rose-600"><Trash2 size={14} /></button></td>
                      </tr>
                    ))}
                    {cameras.length === 0 && <tr><td colSpan={7} className="text-center py-10 text-gray-400 text-sm">No cameras.</td></tr>}
                  </tbody>
                </table>
              </Card>
            </div>
          </TabPanel>
          <TabPanel>
            <div className="mt-4 space-y-3">
              <Button size="sm" icon={Plus} onClick={() => setShowLocForm(true)}>Add Location</Button>
              {showLocForm && <LocationForm storeId={storeId} onSave={() => { setShowLocForm(false); adminListLocations(storeId).then((r) => setLocations(r.data)); flash("Saved"); }} onCancel={() => setShowLocForm(false)} />}
              <Card className="p-0 overflow-hidden">
                <table className="w-full text-sm text-left">
                  <thead>
                    <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
                      <th className="px-5 py-3">Floor</th>
                      <th className="px-5 py-3">Location</th>
                      <th className="px-5 py-3"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {locations.map((l, i) => (
                      <tr key={i} className="hover:bg-slate-50/50">
                        <td className="px-5 py-3">{l.floor_name}</td>
                        <td className="px-5 py-3">{l.location_name}</td>
                        <td className="px-5 py-3"><button onClick={() => delLocation(l.floor_name, l.location_name)} className="text-slate-400 hover:text-rose-600"><Trash2 size={14} /></button></td>
                      </tr>
                    ))}
                    {locations.length === 0 && <tr><td colSpan={3} className="text-center py-10 text-gray-400 text-sm">No locations.</td></tr>}
                  </tbody>
                </table>
              </Card>
            </div>
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}
