import { useEffect, useState } from "react";
import { reportsSummary, reportsWalkins, reportsImageScans, adminListStores } from "../api/client";
import { Card, Title, Text, Badge, TabGroup, TabList, Tab, TabPanels, TabPanel, Select, SelectItem } from "@tremor/react";

function DaySummaryTable({ rows }: { rows: any[] }) {
  if (!rows.length) return <div className="text-center py-12 text-gray-400 text-sm">No data.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead>
          <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
            <th className="px-5 py-3">Store</th>
            <th className="px-5 py-3">Date</th>
            <th className="px-5 py-3">Walk-ins</th>
            <th className="px-5 py-3">Conversions</th>
            <th className="px-5 py-3">Conv. Rate</th>
            <th className="px-5 py-3">Avg Dwell</th>
            <th className="px-5 py-3">Images</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-slate-50/50">
              <td className="px-5 py-3 font-medium text-slate-700">{r.store_id}</td>
              <td className="px-5 py-3">{r.business_date}</td>
              <td className="px-5 py-3">{r.walkins}</td>
              <td className="px-5 py-3">{r.conversions}</td>
              <td className="px-5 py-3">{(r.conversion_rate * 100).toFixed(1)}%</td>
              <td className="px-5 py-3">{r.avg_dwell_mins?.toFixed(1)} min</td>
              <td className="px-5 py-3">{r.relevant_images} / {r.raw_images}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WalkinTable({ rows }: { rows: any[] }) {
  if (!rows.length) return <div className="text-center py-12 text-gray-400 text-sm">No sessions found.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left whitespace-nowrap">
        <thead>
          <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
            <th className="px-5 py-3">Store</th>
            <th className="px-5 py-3">Date</th>
            <th className="px-5 py-3">Role</th>
            <th className="px-5 py-3">Entry Type</th>
            <th className="px-5 py-3">Time Spent</th>
            <th className="px-5 py-3">Gender</th>
            <th className="px-5 py-3">Age Band</th>
            <th className="px-5 py-3">Style</th>
            <th className="px-5 py-3">Engagement</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-slate-50/50">
              <td className="px-5 py-3 font-medium">{r.store_id}</td>
              <td className="px-5 py-3">{r.business_date || r.date}</td>
              <td className="px-5 py-3">
                <Badge color={r.role?.toUpperCase() === "STAFF" ? "blue" : "emerald"}>{r.role || "—"}</Badge>
              </td>
              <td className="px-5 py-3">{r.entry_type || "—"}</td>
              <td className="px-5 py-3">{r.time_spent_mins || "—"} min</td>
              <td className="px-5 py-3">{r.gender || "—"}</td>
              <td className="px-5 py-3">{r.age_band || "—"}</td>
              <td className="px-5 py-3 max-w-[150px] truncate">{r.clothing_style_archetype || "—"}</td>
              <td className="px-5 py-3">{r.engagement_depth || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ImageScanTable({ rows }: { rows: any[] }) {
  if (!rows.length) return <div className="text-center py-12 text-gray-400 text-sm">No scan data.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left whitespace-nowrap">
        <thead>
          <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
            <th className="px-5 py-3">Image</th>
            <th className="px-5 py-3">Date</th>
            <th className="px-5 py-3">Camera</th>
            <th className="px-5 py-3">YOLO</th>
            <th className="px-5 py-3">Persons</th>
            <th className="px-5 py-3">GPT</th>
            <th className="px-5 py-3">Customers</th>
            <th className="px-5 py-3">Staff</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-slate-50/50">
              <td className="px-5 py-3 max-w-[200px] truncate font-mono text-xs">{r.image_name}</td>
              <td className="px-5 py-3">{r.business_date}</td>
              <td className="px-5 py-3">{r.camera_id || "—"}</td>
              <td className="px-5 py-3">
                <Badge color={r.yolo_relevant ? "emerald" : "slate"}>{r.yolo_relevant ? "Relevant" : "Skip"}</Badge>
              </td>
              <td className="px-5 py-3">{r.person_count}</td>
              <td className="px-5 py-3">
                <Badge color={r.gpt_status === "done" ? "emerald" : r.gpt_status === "failed" ? "rose" : "slate"}>
                  {r.gpt_status || "—"}
                </Badge>
              </td>
              <td className="px-5 py-3">{r.customer_count}</td>
              <td className="px-5 py-3">{r.staff_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ReportsPage() {
  const [stores, setStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState("");
  const [summaryRows, setSummaryRows] = useState<any[]>([]);
  const [walkinRows, setWalkinRows] = useState<any[]>([]);
  const [scanRows, setScanRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    adminListStores().then((r) => setStores(r.data));
  }, []);

  useEffect(() => {
    setLoading(true);
    const sid = selectedStore || undefined;
    Promise.all([
      reportsSummary(sid).then((r) => setSummaryRows(r.data)),
      reportsWalkins(sid).then((r) => setWalkinRows(r.data)),
      reportsImageScans(sid).then((r) => setScanRows(r.data)),
    ]).finally(() => setLoading(false));
  }, [selectedStore]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <Title>Reports</Title>
          <Text>Store performance, walk-in sessions, and image scan results.</Text>
        </div>
        <div className="w-56">
          <Select value={selectedStore} onValueChange={setSelectedStore} placeholder="All Stores">
            <SelectItem value="">All Stores</SelectItem>
            {stores.map((s) => (
              <SelectItem key={s.store_id} value={s.store_id}>{s.store_name}</SelectItem>
            ))}
          </Select>
        </div>
      </div>

      <TabGroup>
        <TabList>
          <Tab>Daily Summary</Tab>
          <Tab>Walk-in Sessions</Tab>
          <Tab>Image Scans</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <Card className="mt-4 p-0 overflow-hidden">
              {loading ? <div className="p-8 text-center text-gray-400 text-sm">Loading…</div> : <DaySummaryTable rows={summaryRows} />}
            </Card>
          </TabPanel>
          <TabPanel>
            <Card className="mt-4 p-0 overflow-hidden">
              {loading ? <div className="p-8 text-center text-gray-400 text-sm">Loading…</div> : <WalkinTable rows={walkinRows} />}
            </Card>
          </TabPanel>
          <TabPanel>
            <Card className="mt-4 p-0 overflow-hidden">
              {loading ? <div className="p-8 text-center text-gray-400 text-sm">Loading…</div> : <ImageScanTable rows={scanRows} />}
            </Card>
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}
