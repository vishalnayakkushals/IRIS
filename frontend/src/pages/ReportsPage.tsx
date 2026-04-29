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

const WALKIN_COLS = [
  { key: "Date", label: "Date" },
  { key: "Walk-in ID", label: "Walk-in ID" },
  { key: "Group ID", label: "Group ID" },
  { key: "Role", label: "Role" },
  { key: "Entry Time", label: "Entry Time" },
  { key: "Exit Time", label: "Exit Time" },
  { key: "Time Spent (mins)", label: "Time Spent (mins)" },
  { key: "Session Status", label: "Session Status" },
  { key: "Entry Type", label: "Entry Type" },
  { key: "Gender", label: "Gender" },
  { key: "Age Band", label: "Age Band" },
  { key: "Attire / Visual Marker", label: "Attire / Visual Marker" },
  { key: "Primary Clothing", label: "Primary Clothing" },
  { key: "Jewellery Load", label: "Jewellery Load" },
  { key: "Bag Type", label: "Bag Type" },
  { key: "Primary Clothing Style Archetype", label: "Style Archetype" },
  { key: "Engagement Type", label: "Engagement Type" },
  { key: "Engagement Depth", label: "Depth" },
  { key: "Purchase Signal (Bag)", label: "Purchase Signal" },
  { key: "Included in Analytics", label: "In Analytics" },
];

function roleBadgeColor(role: string) {
  const r = (role || "").toUpperCase();
  if (r === "STAFF") return "blue";
  if (r === "CUSTOMER") return "emerald";
  return "slate";
}

function WalkinTable({ rows, storeMap }: { rows: any[]; storeMap: Record<string, string> }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-left whitespace-nowrap">
        <thead>
          <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
            <th className="px-4 py-3 sticky left-0 bg-slate-50 z-10">Store</th>
            {WALKIN_COLS.map((c) => (
              <th key={c.key} className="px-4 py-3">{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={r.id ?? i} className="hover:bg-slate-50/50">
              <td className="px-4 py-2.5 font-medium text-slate-700 sticky left-0 bg-white z-10 border-r border-slate-100">
                {storeMap[r.store_id] || r.store_id || "—"}
              </td>
              {WALKIN_COLS.map((c) => {
                const val = r[c.key] ?? r[c.key.toLowerCase().replace(/ /g, "_").replace(/[^a-z0-9_]/g, "")] ?? "";
                if (c.key === "Role") return (
                  <td key={c.key} className="px-4 py-2.5">
                    <Badge color={roleBadgeColor(String(val))}>{String(val) || "—"}</Badge>
                  </td>
                );
                if (c.key === "Session Status") return (
                  <td key={c.key} className="px-4 py-2.5">
                    <Badge color={String(val).toUpperCase() === "CLOSED" ? "slate" : "amber"}>{String(val) || "—"}</Badge>
                  </td>
                );
                if (c.key === "Included in Analytics") return (
                  <td key={c.key} className="px-4 py-2.5">
                    <Badge color={String(val).toLowerCase() === "yes" ? "emerald" : "rose"}>{String(val) || "—"}</Badge>
                  </td>
                );
                if (c.key === "Purchase Signal (Bag)") return (
                  <td key={c.key} className="px-4 py-2.5">
                    <Badge color={String(val).toLowerCase() === "yes" ? "emerald" : "slate"}>{String(val) || "—"}</Badge>
                  </td>
                );
                if (c.key === "Attire / Visual Marker") return (
                  <td key={c.key} className="px-4 py-2.5 max-w-[180px] truncate text-slate-600 text-xs" title={String(val)}>
                    {String(val) || "—"}
                  </td>
                );
                return (
                  <td key={c.key} className="px-4 py-2.5 text-slate-700">
                    {String(val) || "—"}
                  </td>
                );
              })}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={WALKIN_COLS.length + 1} className="px-5 py-10 text-center text-gray-400 text-sm">
                No walk-in sessions found for the current filter.
              </td>
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
          <Tab>Datewise Footfall Detail Analysis</Tab>
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
