import { useEffect, useState } from "react";
import { reportsWalkins, adminListStores } from "../api/client";
import { Card, Title, Text, Badge, Select, SelectItem } from "@tremor/react";

function roleBadge(role: string) {
  const r = (role || "").toUpperCase();
  if (r === "STAFF") return <Badge color="blue">Staff</Badge>;
  if (r === "CUSTOMER") return <Badge color="emerald">Customer</Badge>;
  return <Badge color="slate">{role || "Unknown"}</Badge>;
}

function entryBadge(et: string) {
  const e = (et || "").toUpperCase();
  if (e === "BILLING") return <Badge color="violet">Billing</Badge>;
  if (e === "BROWSING") return <Badge color="amber">Browsing</Badge>;
  return <Badge color="slate">{et || "—"}</Badge>;
}

function JourneyCard({ session }: { session: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border rounded-lg bg-white hover:shadow-sm transition-shadow">
      <button
        className="w-full flex items-center justify-between px-5 py-4 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex items-center gap-3 flex-wrap">
          {roleBadge(session.role)}
          {entryBadge(session.entry_type)}
          <span className="text-sm text-slate-600 font-medium">{session.store_id}</span>
          <span className="text-xs text-slate-400">{session.business_date || session.date}</span>
        </div>
        <div className="flex items-center gap-4 text-sm text-slate-500">
          <span>{session.time_spent_mins ? `${session.time_spent_mins} min` : "—"}</span>
          <span className="text-slate-300">{open ? "▲" : "▼"}</span>
        </div>
      </button>

      {open && (
        <div className="border-t px-5 py-4 grid grid-cols-2 md:grid-cols-3 gap-4 text-sm bg-slate-50/50">
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Gender</span>{session.gender || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Age Band</span>{session.age_band || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Style</span>{session.clothing_style_archetype || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Primary Clothing</span>{session.primary_clothing || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Jewellery</span>{session.jewellery_load || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Bag Type</span>{session.bag_type || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Engagement</span>{session.engagement_type || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Depth</span>{session.engagement_depth || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Purchase Signal</span>{session.purchase_signal_bag || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Entry Time</span>{session.entry_time || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Exit Time</span>{session.exit_time || "—"}</div>
          <div><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Camera</span>{session.camera_id || "—"}</div>
          <div className="col-span-full"><span className="text-slate-400 text-xs uppercase tracking-wide block mb-0.5">Attire Marker</span>{session.attire_visual_marker || "—"}</div>
        </div>
      )}
    </div>
  );
}

export default function CustomerJourneys() {
  const [stores, setStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState("");
  const [sessions, setSessions] = useState<any[]>([]);
  const [roleFilter, setRoleFilter] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    adminListStores().then((r) => setStores(r.data));
  }, []);

  useEffect(() => {
    setLoading(true);
    reportsWalkins(selectedStore || undefined, undefined, 300)
      .then((r) => setSessions(r.data))
      .finally(() => setLoading(false));
  }, [selectedStore]);

  const filtered = roleFilter
    ? sessions.filter((s) => (s.role || "").toUpperCase() === roleFilter.toUpperCase())
    : sessions;

  const customers = sessions.filter((s) => (s.role || "").toUpperCase() === "CUSTOMER").length;
  const staff = sessions.filter((s) => (s.role || "").toUpperCase() === "STAFF").length;
  const billing = sessions.filter((s) => (s.entry_type || "").toUpperCase() === "BILLING").length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <Title>Customer Journeys</Title>
          <Text>Individual session details — demographics, engagement, and behavior.</Text>
        </div>
        <div className="flex gap-2">
          <div className="w-44">
            <Select value={selectedStore} onValueChange={setSelectedStore} placeholder="All Stores">
              <SelectItem value="">All Stores</SelectItem>
              {stores.map((s) => <SelectItem key={s.store_id} value={s.store_id}>{s.store_name}</SelectItem>)}
            </Select>
          </div>
          <div className="w-36">
            <Select value={roleFilter} onValueChange={setRoleFilter} placeholder="All Roles">
              <SelectItem value="">All Roles</SelectItem>
              <SelectItem value="CUSTOMER">Customer</SelectItem>
              <SelectItem value="STAFF">Staff</SelectItem>
            </Select>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Customers</Text><p className="text-2xl font-bold mt-1">{customers}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Staff</Text><p className="text-2xl font-bold mt-1">{staff}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Billing</Text><p className="text-2xl font-bold mt-1">{billing}</p></Card>
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading sessions…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">No sessions found.</div>
      ) : (
        <div className="space-y-2">
          {filtered.map((s) => <JourneyCard key={s.id} session={s} />)}
        </div>
      )}
    </div>
  );
}
