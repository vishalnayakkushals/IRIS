import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Download, Play, RefreshCw } from "lucide-react";
import { Badge, Card } from "@tremor/react";
import StoreSelect from "../../components/StoreSelect";
import type { RunRecord } from "../../api/client";

export const STAGE_LABELS: Record<string, string> = {
  DOWNLOAD: "Downloading images from Drive",
  YOLO: "Running YOLO detection",
  GPT: "Running GPT vision analysis",
  DASHBOARD_INGEST: "Saving results to database",
  REPORT: "Generating reports",
  DONE: "Complete",
  "": "Initialising…",
};

function ProgressBar({ value, max, color = "blue" }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const colorClass = color === "emerald" ? "bg-emerald-500" : color === "amber" ? "bg-amber-500" : "bg-blue-500";
  return (
    <div className="w-full bg-slate-100 rounded-full h-2">
      <div className={`${colorClass} h-2 rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function ElapsedTimer({ startedAt }: { startedAt: string }) {
  const [elapsed, setElapsed] = useState("");
  useEffect(() => {
    if (!startedAt) return;
    const update = () => {
      const secs = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
      const m = Math.floor(secs / 60);
      const s = secs % 60;
      setElapsed(`${m}m ${s}s`);
    };
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [startedAt]);
  return <span>{elapsed}</span>;
}

type StoreRecord = { store_id?: string; store_name?: string; [key: string]: any };

type SyncTriggerCardProps = {
  stores: StoreRecord[];
  adminStores: StoreRecord[];
  selectedStore: string;
  syncing: boolean;
  manualSource: string;
  maxImages: number;
  gptEnabled: boolean;
  gptBatchMode: boolean;
  forceReprocess: boolean;
  onSelectedStoreChange: (value: string) => void;
  onManualSourceChange: (value: string) => void;
  onMaxImagesChange: (value: number) => void;
  onGptEnabledChange: (value: boolean) => void;
  onGptBatchModeChange: (value: boolean) => void;
  onForceReprocessChange: (value: boolean) => void;
  onSyncNow: () => void;
  onRefresh: () => void;
};

export function SyncTriggerCard(props: SyncTriggerCardProps) {
  const {
    stores,
    adminStores,
    selectedStore,
    syncing,
    manualSource,
    maxImages,
    gptEnabled,
    gptBatchMode,
    forceReprocess,
    onSelectedStoreChange,
    onManualSourceChange,
    onMaxImagesChange,
    onGptEnabledChange,
    onGptBatchModeChange,
    onForceReprocessChange,
    onSyncNow,
    onRefresh,
  } = props;
  const selectedAdminStore = adminStores.find((s) => s.store_id === selectedStore);
  const selectedSyncStore = stores.find((s) => s.store_id === selectedStore);
  const storeHasUrl = Boolean(selectedSyncStore?.drive_folder_url);
  const effectiveSource = manualSource.trim() || String(selectedSyncStore?.drive_folder_url || "");

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center justify-between gap-2 mb-1">
        <p className="text-sm font-semibold text-slate-700">Run Sync Now</p>
        <p className="text-xs text-slate-400">Select a store, optionally enable GPT, then click Sync Now. Progress updates every 3 seconds.</p>
      </div>
      <div className="flex flex-col md:flex-row md:items-end gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-80">
            <label className="iris-label">Store</label>
            <StoreSelect
              stores={adminStores.map((store) => ({
                store_id: String(store.store_id || ""),
                store_name: String(store.store_name || store.store_id || ""),
              }))}
              value={selectedStore}
              onChange={onSelectedStoreChange}
              placeholder="Select store"
              includeAll={false}
            />
          </div>
          <div className="w-96">
            <label className="iris-label">Manual Folder URL / Folder ID (optional)</label>
            <input type="text" value={manualSource} onChange={(e) => onManualSourceChange(e.target.value)} placeholder="Blank = use mapped parent folder. You can paste a child date-folder URL or raw folder ID." className="iris-input" />
          </div>
          <div className="w-36">
            <label className="iris-label">Max Images</label>
            <input type="number" min={0} step={100} value={maxImages} onChange={(e) => onMaxImagesChange(Number(e.target.value || 0))} className="iris-input" />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer pb-2" title="Controls OpenAI GPT calls for manual syncs and hourly automation. YOLO and reports still run when this is off.">
            <input type="checkbox" checked={gptEnabled} onChange={(e) => onGptEnabledChange(e.target.checked)} className="rounded border-slate-300 text-blue-600" />
            OpenAI GPT calls
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer pb-2" title="Queue images for overnight OpenAI Batch API (50% cost saving). Results ready by morning.">
            <input type="checkbox" checked={gptBatchMode} disabled={!gptEnabled} onChange={(e) => onGptBatchModeChange(e.target.checked)} className="rounded border-slate-300 text-purple-600 disabled:opacity-40" />
            <span className="flex items-center gap-1">Batch mode <span className="text-xs bg-purple-100 text-purple-700 px-1 rounded">50% cheaper</span></span>
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer pb-2">
            <input type="checkbox" checked={forceReprocess} onChange={(e) => onForceReprocessChange(e.target.checked)} className="rounded border-slate-300 text-blue-600" />
            Force rerun / overwrite
          </label>
          <button onClick={onSyncNow} disabled={syncing || !effectiveSource || !selectedStore} className="iris-btn-primary">
            <Play size={14} />
            {syncing ? "Running…" : "Sync Now"}
          </button>
          <button onClick={onRefresh} className="iris-btn-secondary" title="Refresh">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {selectedSyncStore && (
        <div className="pt-3 border-t grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div>
            <p className="iris-label">Source</p>
            <p className={effectiveSource ? "text-slate-600 text-xs truncate max-w-[320px]" : "text-rose-500 text-xs"} title={effectiveSource || "No source configured"}>
              {manualSource.trim() ? "Manual child folder override ready" : storeHasUrl ? "Configured parent folder ✓" : "Not set — go to Admin > Store Mapping"}
            </p>
            {effectiveSource ? <p className="mt-1 text-[10px] text-slate-400 truncate max-w-[320px]" title={effectiveSource}>{effectiveSource}</p> : null}
          </div>
          <div>
            <p className="iris-label">Auto-Sync</p>
            <p className="text-xs text-slate-600">{selectedAdminStore?.sync_enabled ? `Every ${selectedAdminStore.sync_interval_hours || 1}h` : "Disabled"}</p>
          </div>
          <div>
            <p className="iris-label">Last Sync</p>
            <p className="text-xs text-slate-500">{selectedSyncStore.last_sync_at ? new Date(selectedSyncStore.last_sync_at).toLocaleString("en-IN", { hour12: true }) : "Never"}</p>
          </div>
          <div>
            <p className="iris-label">Status</p>
            <Badge color={syncing || selectedSyncStore.is_running ? "amber" : selectedSyncStore.last_status === "ok" ? "emerald" : selectedSyncStore.last_status === "error" ? "rose" : "slate"}>
              {syncing || selectedSyncStore.is_running ? `Running${selectedSyncStore.current_stage ? ` • ${selectedSyncStore.current_stage}` : ""}` : selectedSyncStore.last_status || "Never"}
            </Badge>
            {selectedSyncStore?.last_message ? <p className={`mt-1 max-w-[260px] truncate text-[10px] ${selectedSyncStore.last_status === "error" && !selectedSyncStore.is_running ? "text-rose-500" : "text-slate-400"}`} title={selectedSyncStore.last_message}>{selectedSyncStore.last_message}</p> : null}
          </div>
        </div>
      )}
      <div className="text-xs text-slate-400">Manual sync accepts the mapped parent folder, a child date-folder URL, or a raw Google Drive folder ID. Delta skip still applies unless Force rerun is enabled. 0 = full folder. When OpenAI GPT calls are off, YOLO, relevant-image storage, and scan reports still run, but GPT customer/staff fields are not filled.</div>
    </Card>
  );
}

export function LiveProgressCard({ liveProgress, syncing }: { liveProgress: any; syncing: boolean }) {
  if (!liveProgress || liveProgress.status === "never") return null;
  const progressPct = liveProgress.images_discovered > 0 ? Math.round((liveProgress.images_processed / liveProgress.images_discovered) * 100) : 0;
  return (
    <Card className={`p-5 space-y-4 border-2 ${liveProgress.is_running ? "border-amber-300 bg-amber-50/30" : "border-slate-200"}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-700">
            {liveProgress.is_running ? (
              <span className="flex items-center gap-2"><span className="inline-block h-2 w-2 rounded-full bg-amber-500 animate-pulse" />Pipeline Running — {STAGE_LABELS[liveProgress.stage] || liveProgress.stage}</span>
            ) : (
              <span>Last Run — {liveProgress.status === "done" ? "Completed" : liveProgress.status}</span>
            )}
          </p>
          {liveProgress.is_running && liveProgress.started_at ? <p className="text-xs text-slate-400 mt-0.5">Elapsed: <ElapsedTimer startedAt={liveProgress.started_at} /></p> : null}
          {liveProgress.stale_heartbeat ? <p className="text-xs text-rose-500 mt-1">No heartbeat for {liveProgress.heartbeat_age_seconds}s — possible stall in current stage.</p> : null}
        </div>
        {liveProgress.error ? <div className="flex items-center gap-1 text-rose-600 text-xs max-w-xs truncate"><AlertCircle size={14} /> {liveProgress.error}</div> : null}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="space-y-1"><p className="text-xs text-slate-400 uppercase tracking-wide">Images in Drive</p><p className="text-2xl font-bold text-slate-800">{(liveProgress.images_discovered || 0).toLocaleString()}</p></div>
        <div className="space-y-1"><p className="text-xs text-slate-400 uppercase tracking-wide">Processed</p><p className="text-2xl font-bold text-slate-800">{(liveProgress.images_processed || 0).toLocaleString()}</p></div>
        <div className="space-y-1"><p className="text-xs text-slate-400 uppercase tracking-wide">YOLO Relevant</p><p className="text-2xl font-bold text-emerald-700">{(liveProgress.images_relevant || 0).toLocaleString()}</p></div>
        <div className="space-y-1"><p className="text-xs text-slate-400 uppercase tracking-wide">GPT Done</p><p className="text-2xl font-bold text-blue-700">{(liveProgress.gpt_success || 0).toLocaleString()}</p></div>
      </div>
      {liveProgress.images_discovered > 0 && <div className="space-y-1"><div className="flex justify-between text-xs text-slate-500"><span>Progress</span><span>{progressPct}% — {liveProgress.images_processed} / {liveProgress.images_discovered}</span></div><ProgressBar value={liveProgress.images_processed} max={liveProgress.images_discovered} color="blue" /></div>}
      {liveProgress.images_processed > 0 && liveProgress.images_relevant > 0 && <div className="space-y-1"><div className="flex justify-between text-xs text-slate-500"><span>YOLO relevance</span><span>{Math.round((liveProgress.images_relevant / liveProgress.images_processed) * 100)}% relevant</span></div><ProgressBar value={liveProgress.images_relevant} max={liveProgress.images_processed} color="emerald" /></div>}
      {liveProgress.pending_tasks > 0 ? <p className="text-xs text-amber-600 font-medium">{liveProgress.pending_tasks} tasks pending in queue</p> : null}
      {syncing ? <p className="text-[11px] text-slate-400">Live refresh is active while this run is in progress.</p> : null}
    </Card>
  );
}

export function DateReportCard({ selectedStore, syncing, dateReport, loadingReport, onRefresh }: { selectedStore: string; syncing: boolean; dateReport: any[]; loadingReport: boolean; onRefresh: () => void }) {
  if (!selectedStore) return null;
  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-700">Date-wise Scan Report</p>
          <p className="text-xs text-slate-400 mt-0.5">Images discovered, YOLO processed, relevant, and GPT results per date.</p>
        </div>
        {syncing ? <span className="text-xs text-slate-400">Live auto-refresh every 3s</span> : null}
        <button onClick={onRefresh} className="iris-btn-secondary text-xs px-3 py-1.5"><RefreshCw size={12} /> Refresh</button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
              <th className="px-5 py-3">Date</th><th className="px-5 py-3">Total Images</th><th className="px-5 py-3">YOLO Done</th><th className="px-5 py-3">YOLO Relevant</th><th className="px-5 py-3">Pending</th><th className="px-5 py-3">GPT Done</th><th className="px-5 py-3">GPT Failed</th><th className="px-5 py-3">GPT Disabled</th><th className="px-5 py-3">Customers</th><th className="px-5 py-3">Staff</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loadingReport ? <tr><td colSpan={10} className="px-5 py-8 text-center text-slate-400 text-sm">Loading…</td></tr> : null}
            {!loadingReport && dateReport.map((r) => (
              <tr key={r.date} className="hover:bg-slate-50/50">
                <td className="px-5 py-3 font-medium font-mono text-xs text-slate-700">{r.date}</td>
                <td className="px-5 py-3 font-semibold">{r.total_images.toLocaleString()}</td>
                <td className="px-5 py-3"><div className="flex items-center gap-2"><span>{r.yolo_done.toLocaleString()}</span>{r.total_images > 0 ? <div className="w-16 bg-slate-100 rounded-full h-1.5"><div className="bg-blue-400 h-1.5 rounded-full" style={{ width: `${Math.min(100, Math.round((r.yolo_done / r.total_images) * 100))}%` }} /></div> : null}</div></td>
                <td className="px-5 py-3"><Badge color={r.yolo_relevant > 0 ? "emerald" : "slate"}>{r.yolo_relevant}</Badge></td>
                <td className="px-5 py-3"><Badge color={r.pending_yolo > 0 ? "amber" : "slate"}>{r.pending_yolo}</Badge></td>
                <td className="px-5 py-3"><Badge color={r.gpt_done > 0 ? "blue" : "slate"}>{r.gpt_done}</Badge></td>
                <td className="px-5 py-3"><Badge color={r.gpt_failed > 0 ? "red" : "slate"}>{r.gpt_failed ?? 0}</Badge></td>
                <td className="px-5 py-3"><Badge color={r.gpt_disabled > 0 ? "orange" : "slate"}>{r.gpt_disabled ?? 0}</Badge></td>
                <td className="px-5 py-3 font-semibold text-emerald-700">{r.customers || "—"}</td>
                <td className="px-5 py-3 text-blue-700">{r.staff || "—"}</td>
              </tr>
            ))}
            {!loadingReport && dateReport.length === 0 ? <tr><td colSpan={10} className="px-5 py-10 text-center text-slate-400 text-sm">No scan data for this store yet. Run a sync to populate.</td></tr> : null}
          </tbody>
          {dateReport.length > 0 ? <tfoot><tr className="bg-slate-50 border-t font-semibold text-xs text-slate-600"><td className="px-5 py-3">TOTAL</td><td className="px-5 py-3">{dateReport.reduce((s, r) => s + r.total_images, 0).toLocaleString()}</td><td className="px-5 py-3">{dateReport.reduce((s, r) => s + r.yolo_done, 0).toLocaleString()}</td><td className="px-5 py-3">{dateReport.reduce((s, r) => s + r.yolo_relevant, 0).toLocaleString()}</td><td className="px-5 py-3">{dateReport.reduce((s, r) => s + r.pending_yolo, 0).toLocaleString()}</td><td className="px-5 py-3">{dateReport.reduce((s, r) => s + r.gpt_done, 0).toLocaleString()}</td><td className="px-5 py-3 text-red-600">{dateReport.reduce((s, r) => s + (r.gpt_failed ?? 0), 0).toLocaleString()}</td><td className="px-5 py-3 text-orange-600">{dateReport.reduce((s, r) => s + (r.gpt_disabled ?? 0), 0).toLocaleString()}</td><td className="px-5 py-3 text-emerald-700">{dateReport.reduce((s, r) => s + r.customers, 0).toLocaleString()}</td><td className="px-5 py-3 text-blue-700">{dateReport.reduce((s, r) => s + r.staff, 0).toLocaleString()}</td></tr></tfoot> : null}
        </table>
      </div>
    </Card>
  );
}

export function AutomationStatusCard({ visibleAutomationStores, stores, storeStatusFilter, onStoreStatusFilterChange }: { visibleAutomationStores: StoreRecord[]; stores: StoreRecord[]; storeStatusFilter: "enabled" | "disabled" | "all"; onStoreStatusFilterChange: (value: "enabled" | "disabled" | "all") => void }) {
  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <p className="text-sm font-semibold text-slate-700">All Stores — Automation Status</p>
        <div className="w-full md:w-52">
          <label className="iris-label">Show Stores</label>
          <select className="iris-select" value={storeStatusFilter} onChange={(e) => onStoreStatusFilterChange(e.target.value as "enabled" | "disabled" | "all")}>
            <option value="enabled">Auto-sync enabled</option>
            <option value="disabled">Auto-sync disabled</option>
            <option value="all">All stores</option>
          </select>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead><tr className="bg-slate-50 border-b text-slate-500 font-semibold text-xs tracking-wider uppercase"><th className="px-5 py-3">Store</th><th className="px-5 py-3">Drive</th><th className="px-5 py-3">Auto-Sync</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Last Sync</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {visibleAutomationStores.map((store) => {
              const syncStore = stores.find((s) => s.store_id === store.store_id);
              return (
                <tr key={store.store_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3 font-medium">{store.store_name || store.store_id}</td>
                  <td className="px-5 py-3"><Badge color={syncStore?.drive_folder_url ? "emerald" : "rose"}>{syncStore?.drive_folder_url ? "Ready" : "Missing"}</Badge></td>
                  <td className="px-5 py-3 text-slate-500 text-xs">{store.sync_enabled ? `Every ${store.sync_interval_hours || 1}h` : "Off"}</td>
                  <td className="px-5 py-3"><Badge color={syncStore?.is_running ? "amber" : syncStore?.last_status === "ok" ? "emerald" : syncStore?.last_status === "error" ? "rose" : "slate"}>{syncStore?.is_running ? `Running${syncStore?.current_stage ? ` • ${syncStore.current_stage}` : ""}` : syncStore?.last_status || "Never"}</Badge>{syncStore?.last_message ? <p className="mt-1 max-w-[220px] truncate text-[10px] text-slate-400" title={syncStore.last_message}>{syncStore.last_message}</p> : null}</td>
                  <td className="px-5 py-3 text-slate-400 text-xs">{syncStore?.last_sync_at ? new Date(syncStore.last_sync_at).toLocaleString("en-IN", { hour12: true }) : "Never"}</td>
                </tr>
              );
            })}
            {visibleAutomationStores.length === 0 ? <tr><td colSpan={5} className="px-5 py-10 text-center text-slate-400 text-sm">No stores configured.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function ExecutionHistoryCard({ runs, runLimit, onRunLimitChange, onCleanupZombies, onDownloadRuns, storeNameById }: { runs: RunRecord[]; runLimit: number; onRunLimitChange: (value: number) => void; onCleanupZombies: () => void; onDownloadRuns: () => void; storeNameById: Record<string, string> }) {
  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b flex flex-wrap items-center gap-3">
        <p className="text-sm font-semibold text-slate-700 flex-1">Recent Execution History</p>
        <select className="iris-select text-xs w-32" value={runLimit} onChange={(e) => onRunLimitChange(Number(e.target.value))}>
          <option value={10}>10 rows</option>
          <option value={20}>20 rows</option>
          <option value={50}>50 rows</option>
          <option value={100}>100 rows</option>
        </select>
        <button onClick={onCleanupZombies} className="iris-btn-secondary text-xs px-3 py-1.5" title="Mark all stuck 'running' runs as abandoned"><RefreshCw size={12} /> Clean Stuck Runs</button>
        <button onClick={onDownloadRuns} disabled={!runs.length} className="iris-btn-secondary text-xs px-3 py-1.5"><Download size={12} /> Download CSV</button>
      </div>
      {runs.length === 0 ? (
        <div className="text-center py-12 text-slate-400 text-sm">No runs recorded yet.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead><tr className="bg-slate-50 border-b text-slate-500 font-semibold text-xs tracking-wider uppercase"><th className="px-5 py-3">Job</th><th className="px-5 py-3">Store</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Remarks</th><th className="px-5 py-3">By</th><th className="px-5 py-3">Started</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {runs.map((r) => (
                <tr key={r.run_id} className="hover:bg-slate-50/50">
                  <td className="px-5 py-3 font-medium"><Link to={`/runs/${r.run_id}`} className="hover:text-blue-600 hover:underline">{r.job_name}</Link></td>
                  <td className="px-5 py-3 text-slate-500">{storeNameById[r.store_id] || r.store_id}</td>
                  <td className="px-5 py-3"><Badge color={r.status === "done" ? "emerald" : r.status === "failed" ? "rose" : r.status === "running" ? "amber" : "slate"}>{r.status}</Badge></td>
                  <td className="px-5 py-3 max-w-sm"><span className={`text-xs break-words ${r.status === "failed" ? "text-rose-600 font-medium" : "text-slate-500"}`} title={r.remarks || ""}>{r.remarks || "—"}</span></td>
                  <td className="px-5 py-3 text-slate-400 text-xs">{r.triggered_by}</td>
                  <td className="px-5 py-3 text-slate-400 text-xs">{r.started_at ? new Date(r.started_at).toLocaleString("en-IN", { hour12: true }) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
