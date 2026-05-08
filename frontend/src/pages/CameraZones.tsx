import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  adminListCameras,
  adminUpsertCamera,
  adminDeleteCamera,
  adminDiscoverCameras,
  adminListLocations,
  adminUpsertLocation,
  adminDeleteLocation,
  qaFrameImageUrl,
} from "../api/client";
import { Card, Title, Text, Button, TabGroup, TabList, Tab, TabPanels, TabPanel, Badge } from "@tremor/react";
import { Plus, Trash2, Check, X, ScanSearch, RefreshCw, ZoomIn } from "lucide-react";
import { useStore } from "../context/StoreContext";

const CAM_TYPES = ["unlabeled", "floor", "entry", "external", "skip"] as const;
type CamType = typeof CAM_TYPES[number];

const TYPE_META: Record<CamType, { label: string; color: string; desc: string }> = {
  unlabeled: { label: "Unlabeled", color: "gray",   desc: "Not yet classified — will be analysed" },
  floor:     { label: "Floor",     color: "blue",   desc: "Sales floor camera — full YOLO + GPT analysis" },
  entry:     { label: "Entry",     color: "green",  desc: "Entry / exit gate — full YOLO + GPT analysis" },
  external:  { label: "External",  color: "orange", desc: "Outdoor / parking / non-retail — SKIPPED by pipeline" },
  skip:      { label: "Skip",      color: "red",    desc: "Explicitly excluded from all AI analysis" },
};

const CAM_ROLES = ["INSIDE", "ENTRY", "EXIT", "OUTSIDE"];

function TypeBadge({ type }: { type: CamType }) {
  const m = TYPE_META[type] ?? TYPE_META.unlabeled;
  return <Badge color={m.color as any} size="sm">{m.label}</Badge>;
}

function HoverPreview({ src, rect }: { src: string; rect: DOMRect }) {
  const W = 380, H = 285, margin = 12;
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = rect.right + margin;
  let top  = rect.top + rect.height / 2 - H / 2;
  if (left + W > vw - margin) left = rect.left - W - margin;
  if (top < margin) top = margin;
  if (top + H > vh - margin) top = vh - H - margin;
  return createPortal(
    <div
      className="fixed z-[9999] rounded-xl overflow-hidden border-2 border-white pointer-events-none"
      style={{ left, top, width: W, height: H, boxShadow: "0 24px 64px rgba(0,0,0,0.45)" }}
    >
      <img src={src} alt="preview" className="w-full h-full object-cover" />
    </div>,
    document.body,
  );
}

function CameraThumb({ storeId, imageId }: { storeId: string; imageId: string }) {
  const [hoverRect, setHoverRect] = useState<DOMRect | null>(null);
  const [err, setErr] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  if (!imageId || err) {
    return (
      <div className="w-16 h-12 rounded border bg-slate-100 flex items-center justify-center shrink-0">
        <ZoomIn size={13} className="text-slate-300" />
      </div>
    );
  }
  const src = qaFrameImageUrl(storeId, imageId);
  return (
    <div
      ref={ref}
      className="relative w-16 h-12 rounded overflow-hidden bg-slate-100 cursor-zoom-in shrink-0 group border border-slate-200"
      onMouseEnter={() => setHoverRect(ref.current?.getBoundingClientRect() ?? null)}
      onMouseLeave={() => setHoverRect(null)}
    >
      {hoverRect && <HoverPreview src={src} rect={hoverRect} />}
      <img
        src={src}
        alt="sample"
        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
        loading="lazy"
        onError={() => setErr(true)}
      />
    </div>
  );
}

function InlineTypeSelect({
  storeId, cam, onSaved,
}: { storeId: string; cam: any; onSaved: () => void }) {
  const [saving, setSaving] = useState(false);
  const prev = useRef<string>(cam.camera_type || "unlabeled");

  async function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const newType = e.target.value;
    if (newType === prev.current) return;
    setSaving(true);
    try {
      await adminUpsertCamera(storeId, {
        camera_id: cam.camera_id,
        camera_role: cam.camera_role || "INSIDE",
        floor_name: cam.floor_name || "",
        location_name: cam.location_name || "",
        entry_line_x: cam.entry_line_x ?? 0.5,
        entry_direction: cam.entry_direction || "OUTSIDE_TO_INSIDE",
        camera_type: newType,
        sample_image_id: cam.sample_image_id || "",
      });
      prev.current = newType;
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center gap-1.5">
      <select
        disabled={saving}
        defaultValue={cam.camera_type || "unlabeled"}
        onChange={handleChange}
        className="border rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:opacity-60"
      >
        {CAM_TYPES.map((t) => (
          <option key={t} value={t}>{TYPE_META[t].label}</option>
        ))}
      </select>
      {saving && <span className="text-xs text-slate-400">saving…</span>}
    </div>
  );
}

function CameraAddForm({ storeId, onSave, onCancel }: { storeId: string; onSave: () => void; onCancel: () => void }) {
  const [v, setV] = useState({
    camera_id: "", camera_role: "INSIDE", camera_type: "unlabeled",
    floor_name: "", location_name: "", entry_line_x: 0.5, entry_direction: "OUTSIDE_TO_INSIDE",
  });
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try { await adminUpsertCamera(storeId, v); onSave(); } finally { setSaving(false); }
  }

  return (
    <form onSubmit={submit} className="bg-slate-50 border rounded-lg p-4 space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Camera ID *</label>
          <input className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300" required value={v.camera_id} onChange={(e) => setV({ ...v, camera_id: e.target.value })} placeholder="D01" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Type</label>
          <select className="w-full border rounded px-2 py-1.5 text-sm" value={v.camera_type} onChange={(e) => setV({ ...v, camera_type: e.target.value })}>
            {CAM_TYPES.map((t) => <option key={t} value={t}>{TYPE_META[t].label}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Role</label>
          <select className="w-full border rounded px-2 py-1.5 text-sm" value={v.camera_role} onChange={(e) => setV({ ...v, camera_role: e.target.value })}>
            {CAM_ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Floor</label>
          <input className="w-full border rounded px-2 py-1.5 text-sm" value={v.floor_name} onChange={(e) => setV({ ...v, floor_name: e.target.value })} />
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
  const { storeId } = useStore();
  const [cameras, setCameras] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [showCamForm, setShowCamForm] = useState(false);
  const [showLocForm, setShowLocForm] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [toast, setToast] = useState("");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 4000); }

  function reload() {
    if (!storeId) return;
    adminListCameras(storeId).then((r) => setCameras(r.data));
    adminListLocations(storeId).then((r) => setLocations(r.data));
  }

  useEffect(() => { reload(); }, [storeId]);

  async function discover() {
    if (!storeId) return;
    setDiscovering(true);
    try {
      const r = await adminDiscoverCameras(storeId);
      const { added, existing } = r.data;
      flash(added > 0
        ? `Discovered ${added} new camera${added > 1 ? "s" : ""}. ${existing} already registered.`
        : `All ${existing} cameras already registered. No new cameras found.`
      );
      reload();
    } catch {
      flash("Discover failed — run a pipeline scan first so images exist.");
    } finally {
      setDiscovering(false);
    }
  }

  async function delCamera(cid: string) {
    if (!confirm(`Delete camera ${cid}?`)) return;
    await adminDeleteCamera(storeId, cid);
    flash(`Camera ${cid} deleted`);
    reload();
  }

  async function delLocation(floor: string, loc: string) {
    if (!confirm(`Delete ${floor} / ${loc}?`)) return;
    await adminDeleteLocation(storeId, floor, loc);
    flash("Deleted");
    reload();
  }

  if (!storeId) {
    return (
      <div className="space-y-4">
        <div><Title>Camera Zones</Title><Text>Configure cameras and store location master.</Text></div>
        <div className="border rounded-xl p-10 text-center text-slate-400 text-sm bg-slate-50">
          Select a specific store from the top navigation to manage camera zones.
        </div>
      </div>
    );
  }

  const excluded = cameras.filter((c) => c.camera_type === "external" || c.camera_type === "skip");
  const unlabeled = cameras.filter((c) => !c.camera_type || c.camera_type === "unlabeled");

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg max-w-sm">
          {toast}
        </div>
      )}

      <div className="flex items-start justify-between gap-4">
        <div>
          <Title>Camera Zones</Title>
          <Text>Label each camera to control what gets analysed by AI. Cameras marked <strong>External</strong> or <strong>Skip</strong> are excluded from YOLO and GPT — saving cost.</Text>
        </div>
      </div>

      {/* Summary strip */}
      {cameras.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {(["floor", "entry", "external", "skip"] as CamType[]).map((t) => {
            const count = cameras.filter((c) => c.camera_type === t).length;
            const m = TYPE_META[t];
            return (
              <div key={t} className="border rounded-xl px-4 py-3 bg-white flex items-center justify-between">
                <div>
                  <div className="text-xs text-slate-500 mb-0.5">{m.label}</div>
                  <div className="text-xl font-bold text-slate-800">{count}</div>
                </div>
                <Badge color={m.color as any} size="sm">{t === "external" || t === "skip" ? "Skipped" : "Active"}</Badge>
              </div>
            );
          })}
        </div>
      )}

      {/* Warn about unlabeled */}
      {unlabeled.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800">
          <strong>{unlabeled.length} camera{unlabeled.length > 1 ? "s" : ""} unlabeled.</strong> Set the type for each so the pipeline knows which to skip. External + Skip cameras are excluded from AI analysis.
        </div>
      )}

      {excluded.length > 0 && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 text-sm text-emerald-800">
          <strong>{excluded.length} camera{excluded.length > 1 ? "s" : ""} excluded from AI.</strong> Pipeline will skip YOLO + GPT for: {excluded.map((c) => c.camera_id).join(", ")}
        </div>
      )}

      <TabGroup>
        <TabList><Tab>Cameras ({cameras.length})</Tab><Tab>Locations</Tab></TabList>
        <TabPanels>
          <TabPanel>
            <div className="mt-4 space-y-3">
              <div className="flex gap-2">
                <Button
                  size="sm"
                  icon={ScanSearch}
                  loading={discovering}
                  onClick={discover}
                  color="indigo"
                >
                  Discover from pipeline
                </Button>
                <Button size="sm" icon={Plus} variant="secondary" onClick={() => setShowCamForm(true)}>
                  Add manually
                </Button>
                <Button size="sm" icon={RefreshCw} variant="secondary" onClick={reload}>
                  Refresh
                </Button>
              </div>

              <p className="text-xs text-slate-500">
                Click <strong>Discover from pipeline</strong> to auto-import all cameras found during the last scan. Then set the type for each camera using the dropdown in the table.
              </p>

              {showCamForm && (
                <CameraAddForm
                  storeId={storeId}
                  onSave={() => { setShowCamForm(false); reload(); flash("Saved"); }}
                  onCancel={() => setShowCamForm(false)}
                />
              )}

              <Card className="p-0 overflow-hidden">
                <table className="w-full text-sm text-left">
                  <thead>
                    <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
                      <th className="px-4 py-3">Sample</th>
                      <th className="px-4 py-3">Camera ID</th>
                      <th className="px-4 py-3 min-w-[160px]">Type (click to change)</th>
                      <th className="px-4 py-3">Role</th>
                      <th className="px-4 py-3">Floor</th>
                      <th className="px-4 py-3">Location</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {cameras.map((c) => {
                      const isExcluded = c.camera_type === "external" || c.camera_type === "skip";
                      return (
                        <tr key={c.camera_id} className={`hover:bg-slate-50/50 ${isExcluded ? "opacity-60" : ""}`}>
                          <td className="px-4 py-2">
                            <CameraThumb storeId={storeId} imageId={c.sample_image_id} />
                          </td>
                          <td className="px-4 py-3 font-mono text-sm font-semibold text-slate-700">{c.camera_id}</td>
                          <td className="px-4 py-3">
                            <InlineTypeSelect storeId={storeId} cam={c} onSaved={() => { flash(`${c.camera_id} → ${c.camera_type}`); reload(); }} />
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-500">{c.camera_role || "—"}</td>
                          <td className="px-4 py-3 text-xs">{c.floor_name || "—"}</td>
                          <td className="px-4 py-3 text-xs">{c.location_name || "—"}</td>
                          <td className="px-4 py-3">
                            <button onClick={() => delCamera(c.camera_id)} className="text-slate-300 hover:text-rose-600">
                              <Trash2 size={14} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                    {cameras.length === 0 && (
                      <tr>
                        <td colSpan={7} className="text-center py-14 text-slate-400 text-sm">
                          <ScanSearch size={28} className="mx-auto mb-2 opacity-30" />
                          No cameras yet. Click <strong>Discover from pipeline</strong> after running at least one scan.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </Card>

              {/* Type legend */}
              <div className="grid grid-cols-1 md:grid-cols-5 gap-2 mt-2">
                {CAM_TYPES.map((t) => (
                  <div key={t} className="border rounded-lg px-3 py-2 bg-white text-xs">
                    <TypeBadge type={t} />
                    <p className="text-slate-500 mt-1 leading-snug">{TYPE_META[t].desc}</p>
                  </div>
                ))}
              </div>
            </div>
          </TabPanel>

          <TabPanel>
            <div className="mt-4 space-y-3">
              <Button size="sm" icon={Plus} onClick={() => setShowLocForm(true)}>Add Location</Button>
              {showLocForm && (
                <LocationForm
                  storeId={storeId}
                  onSave={() => { setShowLocForm(false); reload(); flash("Saved"); }}
                  onCancel={() => setShowLocForm(false)}
                />
              )}
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
                        <td className="px-5 py-3">
                          <button onClick={() => delLocation(l.floor_name, l.location_name)} className="text-slate-400 hover:text-rose-600">
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                    {locations.length === 0 && (
                      <tr><td colSpan={3} className="text-center py-10 text-gray-400 text-sm">No locations.</td></tr>
                    )}
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
