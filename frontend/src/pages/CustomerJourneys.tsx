import { useEffect, useState } from "react";
import { reportsWalkins } from "../api/client";
import { Card, Title, Text, Badge } from "@tremor/react";
import { useStore } from "../context/StoreContext";

function roleBadge(role: string) {
  const r = (role || "").toUpperCase();
  if (r === "STAFF") return <Badge color="blue">Staff</Badge>;
  if (r === "CUSTOMER") return <Badge color="emerald">Customer</Badge>;
  if (!role) return null;
  return <Badge color="slate">{role}</Badge>;
}

function entryBadge(et: string) {
  const e = (et || "").toUpperCase();
  if (e === "BILLING") return <Badge color="violet">Billing</Badge>;
  if (e === "BROWSING") return <Badge color="amber">Browsing</Badge>;
  if (!et) return null;
  return <Badge color="slate">{et}</Badge>;
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
  const { storeId: selectedStore, storeName } = useStore();
  const [sessions, setSessions] = useState<any[]>([]);
  const [roleFilter, setRoleFilter] = useState("");
  const [loading, setLoading] = useState(false);

  // Always load — empty selectedStore means all stores (backend returns everything)
  useEffect(() => {
    setLoading(true);
    setSessions([]);
    const limit = selectedStore ? 500 : 1000;
    reportsWalkins(selectedStore || undefined, undefined, limit)
      .then((r) => setSessions(Array.isArray(r.data) ? r.data : []))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, [selectedStore]);

  // Only sessions with a known role are meaningful (GPT-analyzed)
  const meaningful = sessions.filter((s) => (s.role || "").trim() !== "");

  const roleFiltered = roleFilter
    ? meaningful.filter((s) => (s.role || "").toUpperCase() === roleFilter.toUpperCase())
    : meaningful;

  const customers = meaningful.filter((s) => (s.role || "").toUpperCase() === "CUSTOMER").length;
  const staff = meaningful.filter((s) => (s.role || "").toUpperCase() === "STAFF").length;
  const billing = meaningful.filter((s) => (s.entry_type || "").toUpperCase() === "BILLING").length;

  const subtitle = selectedStore
    ? storeName || selectedStore
    : "All Stores";

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <Title>Customer Journeys</Title>
          <Text>Individual session details — {subtitle}</Text>
        </div>
        <div className="flex gap-2">
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="h-9 pl-3 pr-8 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-medium shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 appearance-none cursor-pointer"
          >
            <option value="">All Roles</option>
            <option value="CUSTOMER">Customer</option>
            <option value="STAFF">Staff</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4">
          <Text className="text-xs uppercase tracking-wide text-slate-400">Customers</Text>
          <p className="text-2xl font-bold mt-1">{loading ? "—" : customers}</p>
        </Card>
        <Card className="p-4">
          <Text className="text-xs uppercase tracking-wide text-slate-400">Staff</Text>
          <p className="text-2xl font-bold mt-1">{loading ? "—" : staff}</p>
        </Card>
        <Card className="p-4">
          <Text className="text-xs uppercase tracking-wide text-slate-400">Billing</Text>
          <p className="text-2xl font-bold mt-1">{loading ? "—" : billing}</p>
        </Card>
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading sessions…</div>
      ) : roleFiltered.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">
          {meaningful.length === 0
            ? "No analysed sessions found. Run a GPT pipeline cycle to populate data."
            : "No sessions match the selected role filter."}
        </div>
      ) : (
        <div className="space-y-2">
          {roleFiltered.map((s) => <JourneyCard key={s.id || s.image_id} session={s} />)}
        </div>
      )}
    </div>
  );
}
