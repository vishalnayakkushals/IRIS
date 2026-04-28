import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getJobs, getRuns, onFlyListStores, onFlySync, onFlyStoreStatus } from "../api/client";
import type { JobStatus, RunRecord } from "../api/client";
import JobTable from "../components/JobTable";
import { Play } from "lucide-react";
import { Card, Title, Text, Badge, TabList, Tab, TabGroup, TabPanels, TabPanel, Button, Select, SelectItem } from "@tremor/react";

const POLL_MS = 5000;

export default function SchedulerDashboard() {
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [toast, setToast] = useState("");
  const [stores, setStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState("");
  const [gptEnabled, setGptEnabled] = useState(false);
  const [useTracker, setUseTracker] = useState(false);
  const [syncStatus, setSyncStatus] = useState<any>(null);
  const [syncing, setSyncing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const statusRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadJobs = useCallback(async () => {
    try { const { data } = await getJobs(); setJobs(data); } catch {}
  }, []);

  const loadRuns = useCallback(async () => {
    try { const { data } = await getRuns(20); setRuns(data.runs); } catch {}
  }, []);

  useEffect(() => {
    loadJobs();
    loadRuns();
    onFlyListStores().then((r) => {
      setStores(r.data);
      if (r.data.length && !selectedStore) setSelectedStore(r.data[0].store_id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => { loadJobs(); loadRuns(); }, POLL_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loadJobs, loadRuns]);

  // Poll sync status while running
  useEffect(() => {
    if (!selectedStore) return;
    if (statusRef.current) clearInterval(statusRef.current);
    statusRef.current = setInterval(async () => {
      try {
        const { data } = await onFlyStoreStatus(selectedStore);
        setSyncStatus(data);
        if (!data.is_running) setSyncing(false);
      } catch {}
    }, 3000);
    return () => { if (statusRef.current) clearInterval(statusRef.current); };
  }, [selectedStore]);

  useEffect(() => {
    if (!selectedStore) return;
    onFlyStoreStatus(selectedStore).then((r) => setSyncStatus(r.data)).catch(() => {});
  }, [selectedStore]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 4000);
  }

  async function handleSyncNow() {
    if (!selectedStore) { showToast("Select a store first"); return; }
    const store = stores.find((s) => s.store_id === selectedStore);
    if (!store?.drive_folder_url) {
      showToast("Store has no Drive URL. Configure in Admin > Store Mapping first.");
      return;
    }
    setSyncing(true);
    try {
      const { data } = await onFlySync(selectedStore, { gpt_enabled: gptEnabled, use_tracker: useTracker });
      showToast(data.message || "Sync started");
    } catch (e: any) {
      showToast(e?.response?.data?.detail || "Failed to start sync");
      setSyncing(false);
    }
  }

  async function handleTriggerJob(key: string) {
    showToast(`${key} — legacy Celery trigger (requires Redis worker)`);
  }

  const selectedStoreObj = stores.find((s) => s.store_id === selectedStore);
  const storeHasUrl = Boolean(selectedStoreObj?.drive_folder_url);

  function syncStatusBadge() {
    if (syncing || syncStatus?.is_running) return <Badge color="amber">Running</Badge>;
    if (!syncStatus) return <Badge color="slate">Never synced</Badge>;
    const s = syncStatus.last_status;
    if (s === "ok") return <Badge color="emerald">OK</Badge>;
    if (s === "error") return <Badge color="rose">Error</Badge>;
    return <Badge color="slate">{s || "Never"}</Badge>;
  }

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg opacity-90 transition-opacity">
          {toast}
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <Title>Pipeline Scheduler</Title>
          <Text>Trigger on-fly image sync, YOLO scan, GPT analysis, and view run history.</Text>
        </div>
      </div>

      {/* Store Sync Panel */}
      <Card className="p-5">
        <div className="flex flex-col md:flex-row md:items-end gap-4">
          <div className="flex-1 space-y-1">
            <p className="text-sm font-semibold text-slate-700">Store Sync</p>
            <p className="text-xs text-slate-400">Select a store and trigger the full on-fly pipeline (Drive → YOLO → GPT → Report).</p>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <div className="w-56">
              <Select value={selectedStore} onValueChange={setSelectedStore} placeholder="Select store">
                {stores.map((s) => (
                  <SelectItem key={s.store_id} value={s.store_id}>
                    {s.store_name || s.store_id}
                  </SelectItem>
                ))}
              </Select>
            </div>

            <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
              <input type="checkbox" checked={gptEnabled} onChange={(e) => setGptEnabled(e.target.checked)} />
              GPT analysis
            </label>

            <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
              <input type="checkbox" checked={useTracker} onChange={(e) => setUseTracker(e.target.checked)} />
              BoT-SORT tracker
            </label>

            <Button
              icon={Play}
              size="sm"
              color="blue"
              onClick={handleSyncNow}
              disabled={syncing || !storeHasUrl}
              loading={syncing}
              loadingText="Syncing..."
            >
              {syncing ? "Running..." : "Sync Now"}
            </Button>
          </div>
        </div>

        {selectedStoreObj && (
          <div className="mt-4 pt-4 border-t grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wide mb-0.5">Store</p>
              <p className="font-medium">{selectedStoreObj.store_name}</p>
            </div>
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wide mb-0.5">Drive URL</p>
              <p className={storeHasUrl ? "text-slate-600 text-xs truncate max-w-[200px]" : "text-rose-500 text-xs"}>
                {storeHasUrl ? selectedStoreObj.drive_folder_url : "Not configured — go to Admin > Store Mapping"}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wide mb-0.5">Status</p>
              {syncStatusBadge()}
            </div>
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wide mb-0.5">Last Sync</p>
              <p className="text-xs text-slate-500">
                {syncStatus?.last_sync_at
                  ? new Date(syncStatus.last_sync_at).toLocaleString("en-IN", { hour12: true })
                  : "Never"}
              </p>
            </div>
            {syncStatus?.last_message && (
              <div className="col-span-full">
                <p className="text-xs text-slate-400 uppercase tracking-wide mb-0.5">Last Message</p>
                <p className="text-xs text-slate-500">{syncStatus.last_message}</p>
              </div>
            )}
          </div>
        )}
      </Card>

      <TabGroup>
        <TabList className="mt-4">
          <Tab>Job Queue Status</Tab>
          <Tab>Run History</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <Card className="mt-6">
              <div className="flex items-center justify-between mb-4">
                <Title>Active Queue Status</Title>
                <Text className="text-xs">Auto-refreshes every 5 seconds</Text>
              </div>
              {jobs.length === 0 ? (
                <div className="text-center py-8 text-gray-400 text-sm">Loading pipeline status…</div>
              ) : (
                <JobTable jobs={jobs} onTrigger={handleTriggerJob} />
              )}
            </Card>
          </TabPanel>

          <TabPanel>
            <Card className="mt-6 p-0 border-0 shadow-sm ring-1 ring-slate-200 rounded-lg overflow-hidden">
              <div className="p-4 border-b">
                <Title>Recent Executions</Title>
              </div>
              {runs.length === 0 ? (
                <div className="text-center py-12 text-gray-400 text-sm">No runs recorded.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm whitespace-nowrap">
                    <thead>
                      <tr className="bg-slate-50 border-b text-slate-500 font-semibold text-xs tracking-wider uppercase">
                        <th className="px-6 py-3">Job</th>
                        <th className="px-6 py-3">Status</th>
                        <th className="px-6 py-3">Remarks</th>
                        <th className="px-6 py-3">Triggered By</th>
                        <th className="px-6 py-3">Started</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {runs.map((r) => (
                        <tr key={r.run_id} className="hover:bg-slate-50/50 transition-colors">
                          <td className="px-6 py-4 font-medium text-slate-700">
                            <Link to={`/runs/${r.run_id}`} className="hover:text-blue-600 hover:underline">
                              {r.job_name}
                            </Link>
                          </td>
                          <td className="px-6 py-4">
                            <Badge color={r.status === "done" ? "emerald" : r.status === "failed" ? "rose" : r.status === "running" ? "amber" : "slate"}>
                              {r.status}
                            </Badge>
                          </td>
                          <td className="px-6 py-4 text-slate-500 max-w-xs truncate">{r.remarks || "—"}</td>
                          <td className="px-6 py-4 text-slate-500">{r.triggered_by}</td>
                          <td className="px-6 py-4 text-slate-400 text-xs">
                            {r.started_at ? new Date(r.started_at).toLocaleString("en-IN", { hour12: true }) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}
