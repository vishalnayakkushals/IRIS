import { useCallback, useEffect, useState } from "react";
import { reportsSummary, reportsWalkins, reportsImageScans, adminListStores, onFlyLiveProgress } from "../api/client";
import { Card, Title, Text, Badge, TabGroup, TabList, Tab, TabPanels, TabPanel, Metric } from "@tremor/react";
import StoreSelect from "../components/StoreSelect";

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
  const [liveProgress, setLiveProgress] = useState<any>(null);
  const storeMap = Object.fromEntries(stores.map((store) => [store.store_id, store.store_name || store.store_id]));
  const totalWalkins = summaryRows.reduce((sum, row) => sum + Number(row.walkins || 0), 0);
  const totalConversions = summaryRows.reduce((sum, row) => sum + Number(row.conversions || 0), 0);
  const averageRate = summaryRows.length ? (summaryRows.reduce((sum, row) => sum + Number(row.conversion_rate || 0), 0) / summaryRows.length) : 0;

  const loadReports = useCallback(() => {
    setLoading(true);
    const sid = selectedStore || undefined;
    return Promise.all([
      reportsSummary(sid).then((r) => setSummaryRows(r.data)),
      reportsWalkins(sid, undefined, 300).then((r) => setWalkinRows(r.data)),
      reportsImageScans(sid, undefined, 300).then((r) => setScanRows(r.data)),
    ]).finally(() => setLoading(false));
  }, [selectedStore]);

  useEffect(() => {
    adminListStores().then((r) => setStores(r.data));
  }, []);

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  useEffect(() => {
    let timer: number | undefined;
    async function refreshLive() {
      if (!selectedStore) {
        setLiveProgress(null);
        return;
      }
      try {
        const { data } = await onFlyLiveProgress(selectedStore);
        setLiveProgress(data);
        if (data?.is_running || data?.status === "running") {
          void loadReports();
        }
      } catch {
        setLiveProgress(null);
      }
    }
    void refreshLive();
    timer = window.setInterval(() => {
      void refreshLive();
    }, 5000);
    return () => {
      if (timer) window.clearInterval(timer);
    };
  }, [loadReports, selectedStore]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <Title>Management Reports</Title>
          <Text>Management-ready daily summary, footfall detail, and image scanning output from the live pipeline.</Text>
          {selectedStore && liveProgress && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <Badge color={liveProgress.is_running ? "amber" : liveProgress.status === "failed" ? "rose" : "emerald"}>
                {liveProgress.is_running ? `Live Sync: ${liveProgress.stage || "running"}` : liveProgress.status || "idle"}
              </Badge>
              <span className="text-slate-500">
                Auto-refresh every 5s
              </span>
              {liveProgress.images_discovered ? (
                <span className="text-slate-400">
                  {liveProgress.images_processed || 0} / {liveProgress.images_discovered} processed
                </span>
              ) : null}
              {liveProgress.error ? <span className="text-rose-500 truncate max-w-[18rem]">{liveProgress.error}</span> : null}
            </div>
          )}
        </div>
        <div className="w-full sm:w-80">
          <StoreSelect
            stores={stores}
            value={selectedStore}
            onChange={setSelectedStore}
            includeAll
            allLabel="All Stores"
            placeholder="Filter reports by store"
          />
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
