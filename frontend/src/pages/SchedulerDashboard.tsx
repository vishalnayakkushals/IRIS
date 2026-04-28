import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { adminListStores, getRuns, onFlyListStores, onFlySync, onFlyStoreStatus } from "../api/client";
import type { RunRecord } from "../api/client";
import { Play } from "lucide-react";
import { Card, Title, Text, Badge, Button, Select, SelectItem, Metric } from "@tremor/react";

const POLL_MS = 5000;

export default function SchedulerDashboard() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [toast, setToast] = useState("");
  const [stores, setStores] = useState<any[]>([]);
  const [adminStores, setAdminStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState("");
  const [gptEnabled, setGptEnabled] = useState(false);
  const [useTracker, setUseTracker] = useState(false);
  const [syncStatus, setSyncStatus] = useState<any>(null);
  const [syncing, setSyncing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const statusRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadRuns = useCallback(async () => {
    try { const { data } = await getRuns(20); setRuns(data.runs); } catch {}
  }, []);

  const loadStores = useCallback(async () => {
    try {
      const [syncStoreResponse, adminStoreResponse] = await Promise.all([
        onFlyListStores(),
        adminListStores(),
      ]);
      setStores(syncStoreResponse.data);
      setAdminStores(adminStoreResponse.data);
      if (syncStoreResponse.data.length && !selectedStore) setSelectedStore(syncStoreResponse.data[0].store_id);
    } catch {}
  }, [selectedStore]);

  useEffect(() => {
    loadRuns();
    loadStores();
  }, [loadRuns, loadStores]);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => { loadRuns(); loadStores(); }, POLL_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loadRuns, loadStores]);

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

  const selectedStoreObj = stores.find((s) => s.store_id === selectedStore);
  const selectedAdminStore = adminStores.find((s) => s.store_id === selectedStore);
  const storeHasUrl = Boolean(selectedStoreObj?.drive_folder_url);
  const runningCount = stores.filter((store) => store.is_running).length;
  const driveReadyCount = stores.filter((store) => Boolean(store.drive_folder_url)).length;
  const autoSyncCount = adminStores.filter((store) => Boolean(store.sync_enabled)).length;
  const lastCompletedRun = runs.find((run) => run.status === "done");
  const storeNameById = Object.fromEntries(stores.map((store) => [store.store_id, store.store_name || store.store_id]));

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
          <Title>IRIS Data Sync Console</Title>
          <Text>Manage nightly automation, trigger manual store sync, and review recent execution behaviour in one guided view.</Text>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card decoration="top" decorationColor="blue">
          <Text>Stores Configured</Text>
          <Metric>{adminStores.length}</Metric>
        </Card>
        <Card decoration="top" decorationColor="emerald">
          <Text>Drive Ready</Text>
          <Metric>{driveReadyCount}</Metric>
        </Card>
        <Card decoration="top" decorationColor="amber">
          <Text>Auto-Sync Enabled</Text>
          <Metric>{autoSyncCount}</Metric>
        </Card>
        <Card decoration="top" decorationColor="rose">
          <Text>Running Right Now</Text>
          <Metric>{runningCount}</Metric>
        </Card>
      </div>

      <Card className="p-5 space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <Title>IRIS Data Sync Status</Title>
            <Text>Use this section to understand whether the store is ready, when it last ran, and whether it is part of nightly automation.</Text>
          </div>
          {lastCompletedRun && (
            <div className="rounded-lg border bg-slate-50 px-4 py-3 text-sm">
              <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">Latest successful run</p>
              <p className="font-medium text-slate-700">{lastCompletedRun.job_name}</p>
              <p className="text-xs text-slate-500">{new Date(lastCompletedRun.completed_at || lastCompletedRun.started_at).toLocaleString("en-IN", { hour12: true })}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Store Sync Panel */}
      <Card className="p-5">
        <div className="flex flex-col md:flex-row md:items-end gap-4">
          <div className="flex-1 space-y-1">
            <p className="text-sm font-semibold text-slate-700">Run Data Sync Now</p>
            <p className="text-xs text-slate-400">Choose one store, decide whether GPT and tracking are needed, then start the full web-controlled sync.</p>
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
              <p className="text-xs text-slate-400 uppercase tracking-wide mb-0.5">Night Automation</p>
              <p className="text-xs text-slate-600">
                {selectedAdminStore?.sync_enabled ? `Enabled every ${selectedAdminStore.sync_interval_hours || 1} hour(s)` : "Disabled"}
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

      <Card className="p-0 border-0 shadow-sm ring-1 ring-slate-200 rounded-lg overflow-hidden">
        <div className="p-4 border-b">
          <Title>Store Automation View</Title>
          <Text className="text-xs text-slate-500 mt-1">This tells management which stores are ready for nightly sync and which stores still need Drive mapping.</Text>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead>
              <tr className="bg-slate-50 border-b text-slate-500 font-semibold text-xs tracking-wider uppercase">
                <th className="px-6 py-3">Store</th>
                <th className="px-6 py-3">Drive</th>
                <th className="px-6 py-3">Auto-Sync</th>
                <th className="px-6 py-3">Current Status</th>
                <th className="px-6 py-3">Last Sync</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {adminStores.map((store) => {
                const syncStore = stores.find((item) => item.store_id === store.store_id);
                return (
                  <tr key={store.store_id} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-4 font-medium text-slate-700">{store.store_name || store.store_id}</td>
                    <td className="px-6 py-4">
                      <Badge color={syncStore?.drive_folder_url ? "emerald" : "rose"}>{syncStore?.drive_folder_url ? "Ready" : "Missing"}</Badge>
                    </td>
                    <td className="px-6 py-4 text-slate-500">{store.sync_enabled ? `Enabled every ${store.sync_interval_hours || 1} hour(s)` : "Disabled"}</td>
                    <td className="px-6 py-4">
                      <Badge color={syncStore?.is_running ? "amber" : syncStore?.last_status === "ok" ? "emerald" : syncStore?.last_status === "error" ? "rose" : "slate"}>
                        {syncStore?.is_running ? "Running" : syncStore?.last_status || "Never"}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-slate-400 text-xs">
                      {syncStore?.last_sync_at ? new Date(syncStore.last_sync_at).toLocaleString("en-IN", { hour12: true }) : "Never"}
                    </td>
                  </tr>
                );
              })}
              {adminStores.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-10 text-center text-gray-400 text-sm">No stores are configured yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="p-0 border-0 shadow-sm ring-1 ring-slate-200 rounded-lg overflow-hidden">
        <div className="p-4 border-b">
          <Title>Scheduler Execution History</Title>
        </div>
        {runs.length === 0 ? (
          <div className="text-center py-12 text-gray-400 text-sm">No runs recorded.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead>
                <tr className="bg-slate-50 border-b text-slate-500 font-semibold text-xs tracking-wider uppercase">
                  <th className="px-6 py-3">Run</th>
                  <th className="px-6 py-3">Store</th>
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
                    <td className="px-6 py-4 text-slate-500">{storeNameById[r.store_id] || r.store_id}</td>
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
    </div>
  );
}
