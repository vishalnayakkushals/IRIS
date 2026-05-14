import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { adminCleanupZombieRuns, adminListStores, getRuns, onFlyDateReport, onFlyDownloadRelevantReviewTable, onFlyExportRelevantReviewTable, onFlyGetGptControl, onFlyListStores, onFlyLiveProgress, onFlySync, onFlyUpdateGptControl } from "../api/client";
import { useStore } from "../context/StoreContext";
import type { RelevantReviewTableResult, RunRecord } from "../api/client";
import { Card, Metric, Text, Title } from "@tremor/react";
import { AutomationStatusCard, DateReportCard, ExecutionHistoryCard, LiveProgressCard, RelevantReviewTableCard, SyncTriggerCard } from "../features/scheduler/sections";

const POLL_MS = 3000;

export default function SchedulerDashboard() {
  const { storeId: globalStoreId } = useStore();
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [toast, setToast] = useState("");
  const [stores, setStores] = useState<any[]>([]);
  const [adminStores, setAdminStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState(globalStoreId);
  const [gptEnabled, setGptEnabled] = useState(false);
  const [gptBatchMode, setGptBatchMode] = useState(false);
  const [manualSource, setManualSource] = useState("");
  const [maxImages, setMaxImages] = useState(10000);
  const [forceReprocess, setForceReprocess] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [liveProgress, setLiveProgress] = useState<any>(null);
  const [dateReport, setDateReport] = useState<any[]>([]);
  const [loadingReport, setLoadingReport] = useState(false);
  const [reviewDate, setReviewDate] = useState("");
  const [reviewExporting, setReviewExporting] = useState(false);
  const [lastReviewExport, setLastReviewExport] = useState<RelevantReviewTableResult | null>(null);
  const [storeStatusFilter, setStoreStatusFilter] = useState<"enabled" | "disabled" | "all">("enabled");
  const [runLimit, setRunLimit] = useState(10);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);
  const autoExportRunIdRef = useRef("");

  useEffect(() => {
    setSelectedStore(globalStoreId);
  }, [globalStoreId]);

  const loadRuns = useCallback(async () => {
    try {
      const { data } = await getRuns(runLimit);
      setRuns(data.runs);
    } catch {
      // keep current UI state if the run list fetch fails transiently
    }
  }, [runLimit]);

  const loadStores = useCallback(async () => {
    try {
      const [syncResponse, adminResponse] = await Promise.all([onFlyListStores(), adminListStores()]);
      setStores(syncResponse.data);
      setAdminStores(adminResponse.data);
    } catch {
      // keep prior store list until the next successful poll
    }
  }, []);

  const loadGptControl = useCallback(async () => {
    try {
      const { data } = await onFlyGetGptControl();
      setGptEnabled(Boolean(data.enabled));
      if (!data.enabled) setGptBatchMode(false);
    } catch {
      setGptEnabled(false);
      setGptBatchMode(false);
    }
  }, []);

  const loadProgress = useCallback(async (storeId: string) => {
    if (!storeId) return;
    try {
      const { data } = await onFlyLiveProgress(storeId);
      setLiveProgress(data);
      setSyncing(Boolean(data.is_running || data.status === "running"));
    } catch {
      // do not clear current progress card on a transient refresh miss
    }
  }, []);

  const loadDateReport = useCallback(async (storeId: string, options?: { silent?: boolean }) => {
    if (!storeId) return;
    const silent = Boolean(options?.silent);
    if (!silent) setLoadingReport(true);
    try {
      const { data } = await onFlyDateReport(storeId);
      setDateReport(data);
    } catch {
      // preserve current table until next successful refresh
    } finally {
      if (!silent) setLoadingReport(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();
    loadStores();
    loadGptControl();
  }, [loadRuns, loadStores, loadGptControl]);

  useEffect(() => {
    if (!selectedStore) return;
    setManualSource("");
    setMaxImages(10000);
    setForceReprocess(false);
    setReviewDate("");
    setLastReviewExport(null);
    loadProgress(selectedStore);
    loadDateReport(selectedStore);
  }, [selectedStore, loadProgress, loadDateReport]);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      pollCountRef.current += 1;
      loadRuns();
      if (selectedStore) {
        loadProgress(selectedStore);
        loadDateReport(selectedStore, { silent: true });
      }
      if (pollCountRef.current % 5 === 0) loadStores();
    }, POLL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [loadRuns, loadStores, selectedStore, loadProgress, loadDateReport]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 4000);
  }

  function downloadBlob(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }

  async function handleGptEnabledChange(enabled: boolean) {
    setGptEnabled(enabled);
    if (!enabled) setGptBatchMode(false);
    try {
      const { data } = await onFlyUpdateGptControl(enabled);
      setGptEnabled(Boolean(data.enabled));
      if (!data.enabled) setGptBatchMode(false);
      showToast(data.message || (data.enabled ? "OpenAI GPT calls enabled" : "OpenAI GPT calls disabled"));
    } catch {
      setGptEnabled(false);
      setGptBatchMode(false);
      showToast("Could not update OpenAI GPT setting");
    }
  }

  async function handleSyncNow() {
    if (!selectedStore) {
      showToast("Select a store first");
      return;
    }
    const store = stores.find((s) => s.store_id === selectedStore);
    const effectiveSource = manualSource.trim() || store?.drive_folder_url || "";
    if (!effectiveSource) {
      showToast("Store has no Drive URL — configure in Admin > Store Mapping first");
      return;
    }
    if (maxImages < 0 || maxImages > 10000) {
      showToast("Max images must be between 0 and 10000 (0 = full folder)");
      return;
    }

    setSyncing(true);
    setLiveProgress({
      store_id: selectedStore,
      active_run_id: "",
      run_id: "",
      is_running: true,
      status: "running",
      stage: "",
      images_discovered: 0,
      images_processed: 0,
      images_relevant: 0,
      images_skipped: 0,
      gpt_success: 0,
      gpt_failed: 0,
      pending_tasks: 0,
      error: "",
      stale_heartbeat: false,
    });

    try {
      const { data } = await onFlySync(selectedStore, {
        gpt_enabled: gptEnabled,
        gpt_batch_mode: gptBatchMode,
        source_url: manualSource.trim() || undefined,
        max_images: maxImages,
        force_reprocess: forceReprocess,
      });
      showToast(data.message || "Sync started");
      setLiveProgress((prev: any) => ({ ...(prev || {}), ...data, run_id: data.run_id, active_run_id: data.run_id, is_running: true, status: "running", stage: "" }));
      setTimeout(() => {
        loadProgress(selectedStore);
        loadDateReport(selectedStore, { silent: true });
        loadStores();
      }, 1500);
    } catch (error: any) {
      showToast(error?.response?.data?.detail || "Failed to start sync");
      setSyncing(false);
    }
  }

  const handleExportRelevantReviewTable = useCallback(async (dateOverride?: string) => {
    if (!selectedStore) {
      showToast("Select a store first");
      return;
    }
    const date = typeof dateOverride === "string" ? dateOverride : reviewDate;
    setReviewExporting(true);
    try {
      const { data } = await onFlyExportRelevantReviewTable(selectedStore, date || undefined);
      setLastReviewExport(data);
      const download = await onFlyDownloadRelevantReviewTable(selectedStore, date || undefined);
      downloadBlob(download.data, data.filename || `yolo_relevant_review_table_${date || "all_dates"}.csv`);
      showToast(data.message || `Exported ${data.rows} YOLO-relevant image row(s)`);
    } catch (error: any) {
      showToast(error?.response?.data?.detail || "Could not export YOLO review CSV");
    } finally {
      setReviewExporting(false);
    }
  }, [reviewDate, selectedStore]);

  async function handleRunYoloFullFolder() {
    if (!selectedStore) {
      showToast("Select a store first");
      return;
    }
    const store = stores.find((s) => s.store_id === selectedStore);
    const effectiveSource = manualSource.trim() || store?.drive_folder_url || "";
    if (!effectiveSource) {
      showToast("Store has no Drive URL — configure in Admin > Store Mapping first");
      return;
    }

    setGptEnabled(false);
    setGptBatchMode(false);
    setMaxImages(0);
    setSyncing(true);
    setLiveProgress({
      store_id: selectedStore,
      active_run_id: "",
      run_id: "",
      is_running: true,
      status: "running",
      stage: "",
      images_discovered: 0,
      images_processed: 0,
      images_relevant: 0,
      images_skipped: 0,
      gpt_success: 0,
      gpt_failed: 0,
      pending_tasks: 0,
      error: "",
      stale_heartbeat: false,
    });

    try {
      await onFlyUpdateGptControl(false);
      const { data } = await onFlySync(selectedStore, {
        gpt_enabled: false,
        gpt_batch_mode: false,
        source_url: manualSource.trim() || undefined,
        max_images: 0,
        force_reprocess: forceReprocess,
      });
      autoExportRunIdRef.current = data.run_id || "";
      showToast("Full-folder YOLO started. Review CSV will download after this run finishes.");
      setLiveProgress((prev: any) => ({ ...(prev || {}), ...data, run_id: data.run_id, active_run_id: data.run_id, is_running: true, status: "running", stage: "" }));
      setTimeout(() => {
        loadProgress(selectedStore);
        loadDateReport(selectedStore, { silent: true });
        loadStores();
      }, 1500);
    } catch (error: any) {
      showToast(error?.response?.data?.detail || "Failed to start full-folder YOLO");
      autoExportRunIdRef.current = "";
      setSyncing(false);
    }
  }

  useEffect(() => {
    const pendingRunId = autoExportRunIdRef.current;
    if (!pendingRunId || !selectedStore || !liveProgress) return;
    const progressRunId = String(liveProgress.run_id || liveProgress.active_run_id || "");
    if (progressRunId && progressRunId !== pendingRunId) return;
    const status = String(liveProgress.status || "").toLowerCase();
    const stillRunning = Boolean(liveProgress.is_running || status === "running");
    const terminal = ["done", "success", "completed", "failed", "cancelled", "abandoned", "partial"].includes(status);
    if (!stillRunning && terminal) {
      autoExportRunIdRef.current = "";
      void handleExportRelevantReviewTable();
    }
  }, [handleExportRelevantReviewTable, liveProgress, selectedStore]);

  const runningCount = stores.filter((s) => s.is_running).length;
  const driveReadyCount = stores.filter((s) => Boolean(s.drive_folder_url)).length;
  const autoSyncCount = adminStores.filter((s) => Boolean(s.sync_enabled)).length;
  const visibleAutomationStores = adminStores.filter((store) => {
    if (storeStatusFilter === "enabled") return Boolean(store.sync_enabled);
    if (storeStatusFilter === "disabled") return !store.sync_enabled;
    return true;
  });
  const storeNameById = useMemo(() => Object.fromEntries(stores.map((s) => [s.store_id, s.store_name || s.store_id])), [stores]);

  async function handleCleanupZombies() {
    try {
      const response = await adminCleanupZombieRuns();
      showToast(`Cleaned ${response.data.cleaned} stuck run(s)`);
      loadRuns();
    } catch {
      showToast("Cleanup failed");
    }
  }

  async function downloadRuns() {
    const escape = (value: any) => {
      const stringValue = String(value ?? "");
      return stringValue.includes(",") || stringValue.includes('"') || stringValue.includes("\n") ? `"${stringValue.replace(/"/g, '""')}"` : stringValue;
    };
    const headers = ["Job", "Store", "Status", "Remarks", "Triggered By", "Started At", "Completed At"];
    let allRuns: RunRecord[] = [];
    try {
      const response = await getRuns(10000);
      allRuns = response.data?.runs ?? [];
    } catch {
      allRuns = runs;
    }
    const csvRows = allRuns.map((run) => [
      run.job_name,
      storeNameById[run.store_id] || run.store_id,
      run.status,
      run.remarks || "",
      run.triggered_by,
      run.started_at ? new Date(run.started_at).toLocaleString("en-IN") : "",
      run.completed_at ? new Date(run.completed_at).toLocaleString("en-IN") : "",
    ].map(escape).join(","));
    const csv = [headers.join(","), ...csvRows].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `execution_history_all_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      {toast ? <div className="iris-toast">{toast}</div> : null}

      <div>
        <Title>Scheduler / Pipeline</Title>
        <Text>Trigger manual syncs, monitor live progress, and review date-wise scan results.</Text>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card decoration="top" decorationColor="blue"><Text>Stores Configured</Text><Metric>{adminStores.length}</Metric></Card>
        <Card decoration="top" decorationColor="emerald"><Text>Drive Ready</Text><Metric>{driveReadyCount}</Metric></Card>
        <Card decoration="top" decorationColor="amber"><Text>Auto-Sync On</Text><Metric>{autoSyncCount}</Metric></Card>
        <Card decoration="top" decorationColor={runningCount > 0 ? "rose" : "slate"}><Text>Running Now</Text><Metric>{runningCount}</Metric></Card>
      </div>

      <SyncTriggerCard
        stores={stores}
        adminStores={adminStores}
        selectedStore={selectedStore}
        syncing={syncing}
        manualSource={manualSource}
        maxImages={maxImages}
        gptEnabled={gptEnabled}
        gptBatchMode={gptBatchMode}
        forceReprocess={forceReprocess}
        onSelectedStoreChange={(next) => { setSelectedStore(next); setLiveProgress(null); setDateReport([]); setReviewDate(""); setLastReviewExport(null); }}
        onManualSourceChange={setManualSource}
        onMaxImagesChange={setMaxImages}
        onGptEnabledChange={(value) => void handleGptEnabledChange(value)}
        onGptBatchModeChange={setGptBatchMode}
        onForceReprocessChange={setForceReprocess}
        onSyncNow={() => void handleSyncNow()}
        onRefresh={() => { if (selectedStore) { void loadProgress(selectedStore); void loadDateReport(selectedStore); } void loadRuns(); void loadStores(); }}
      />

      <LiveProgressCard liveProgress={liveProgress} syncing={syncing} />
      <RelevantReviewTableCard
        selectedStore={selectedStore || ""}
        dateReport={dateReport}
        selectedDate={reviewDate}
        exporting={reviewExporting}
        syncing={syncing}
        lastExport={lastReviewExport}
        onDateChange={setReviewDate}
        onRunFullFolder={() => void handleRunYoloFullFolder()}
        onExport={() => void handleExportRelevantReviewTable()}
      />
      <DateReportCard selectedStore={selectedStore || ""} syncing={syncing} dateReport={dateReport} loadingReport={loadingReport} onRefresh={() => { if (selectedStore) void loadDateReport(selectedStore); }} />
      <AutomationStatusCard visibleAutomationStores={visibleAutomationStores} stores={stores} storeStatusFilter={storeStatusFilter} onStoreStatusFilterChange={setStoreStatusFilter} />
      <ExecutionHistoryCard runs={runs} runLimit={runLimit} onRunLimitChange={setRunLimit} onCleanupZombies={() => void handleCleanupZombies()} onDownloadRuns={() => void downloadRuns()} storeNameById={storeNameById} />
    </div>
  );
}
