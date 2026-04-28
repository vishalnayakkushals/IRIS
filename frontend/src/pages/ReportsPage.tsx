import { useEffect, useState } from "react";
import { reportsSummary, reportsWalkins, reportsImageScans, adminListStores } from "../api/client";
import { Card, Title, Text, Badge, TabGroup, TabList, Tab, TabPanels, TabPanel, Select, SelectItem, Metric } from "@tremor/react";

function DaySummaryTable({ rows, storeMap }: { rows: any[]; storeMap: Record<string, string> }) {
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
              <td className="px-5 py-3 font-medium text-slate-700">{storeMap[r.store_id] || r.store_id}</td>
              <td className="px-5 py-3">{r.business_date}</td>
              <td className="px-5 py-3">{r.walkins}</td>
              <td className="px-5 py-3">{r.conversions}</td>
              <td className="px-5 py-3">{(r.conversion_rate * 100).toFixed(1)}%</td>
              <td className="px-5 py-3">{r.avg_dwell_mins?.toFixed(1)} min</td>
              <td className="px-5 py-3">{r.relevant_images} / {r.raw_images}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7} className="px-5 py-10 text-center text-gray-400 text-sm">No summary data available for the current filter.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function WalkinTable({ rows, storeMap }: { rows: any[]; storeMap: Record<string, string> }) {
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
              <td className="px-5 py-3 font-medium">{storeMap[r.store_id] || r.store_id}</td>
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
          {rows.length === 0 && (
            <tr>
              <td colSpan={9} className="px-5 py-10 text-center text-gray-400 text-sm">No walk-in sessions found for the current filter.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ImageScanTable({ rows, storeMap }: { rows: any[]; storeMap: Record<string, string> }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left whitespace-nowrap">
        <thead>
          <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
            <th className="px-5 py-3">Store</th>
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
              <td className="px-5 py-3 font-medium">{storeMap[r.store_id] || r.store_id}</td>
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
          {rows.length === 0 && (
            <tr>
              <td colSpan={9} className="px-5 py-10 text-center text-gray-400 text-sm">No image scan results found for the current filter.</td>
            </tr>
          )}
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
  const storeMap = Object.fromEntries(stores.map((store) => [store.store_id, store.store_name || store.store_id]));
  const totalWalkins = summaryRows.reduce((sum, row) => sum + Number(row.walkins || 0), 0);
  const totalConversions = summaryRows.reduce((sum, row) => sum + Number(row.conversions || 0), 0);
  const averageRate = summaryRows.length ? (summaryRows.reduce((sum, row) => sum + Number(row.conversion_rate || 0), 0) / summaryRows.length) : 0;

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
          <Title>Management Reports</Title>
          <Text>Management-ready daily summary, footfall detail, and image scanning output from the live pipeline.</Text>
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

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card decoration="top" decorationColor="blue">
          <Text>Total Walk-ins In View</Text>
          <Metric>{loading ? "—" : totalWalkins.toLocaleString()}</Metric>
        </Card>
        <Card decoration="top" decorationColor="emerald">
          <Text>Total Conversions In View</Text>
          <Metric>{loading ? "—" : totalConversions.toLocaleString()}</Metric>
        </Card>
        <Card decoration="top" decorationColor="amber">
          <Text>Average Conversion Rate</Text>
          <Metric>{loading ? "—" : `${(averageRate * 100).toFixed(1)}%`}</Metric>
        </Card>
      </div>

      <TabGroup>
        <TabList>
          <Tab>Store Summary</Tab>
          <Tab>Datewise Footfall Detail</Tab>
          <Tab>Image Scanning Result Details</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <Card className="mt-4 p-0 overflow-hidden">
              {loading ? <div className="p-8 text-center text-gray-400 text-sm">Loading…</div> : <DaySummaryTable rows={summaryRows} storeMap={storeMap} />}
            </Card>
          </TabPanel>
          <TabPanel>
            <Card className="mt-4 p-0 overflow-hidden">
              {loading ? <div className="p-8 text-center text-gray-400 text-sm">Loading…</div> : <WalkinTable rows={walkinRows} storeMap={storeMap} />}
            </Card>
          </TabPanel>
          <TabPanel>
            <Card className="mt-4 p-0 overflow-hidden">
              {loading ? <div className="p-8 text-center text-gray-400 text-sm">Loading…</div> : <ImageScanTable rows={scanRows} storeMap={storeMap} />}
            </Card>
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}
