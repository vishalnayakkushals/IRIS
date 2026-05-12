import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { reportsSummary, reportsWalkins, reportsImageScans, reportsValidationMap, onFlyLiveProgress, reportsExportStart, reportsExportStatus, reportsExportDownload } from "../api/client";
import { Card, Title, Text, Badge, Metric } from "@tremor/react";
import { useStore } from "../context/StoreContext";
import { RefreshCw } from "lucide-react";
import {
  DaySummaryTable,
  DownloadBtn,
  ImageScanTable,
  ToastItem,
  ToastStack,
  ValidationTable,
  WalkinTable,
  cacheKey,
  readCache,
  triggerDownload,
  writeCache,
} from "../features/reports/reportHelpers";

export default function ReportsPage() {
  const { storeId: selectedStore, stores } = useStore();
  const [reportBucket, setReportBucket] = useState<"main" | "validation">("main");
  const [reportView, setReportView] = useState("summary");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [summaryRows, setSummaryRows] = useState<any[]>([]);
  const [walkinRows, setWalkinRows] = useState<any[]>([]);
  const [scanRows, setScanRows] = useState<any[]>([]);
  const [validationRows, setValidationRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [liveProgress, setLiveProgress] = useState<any>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [exportingTab, setExportingTab] = useState<string | null>(null);
  const [scanFacility, setScanFacility] = useState<string>("");
  const [fetchedTabs, setFetchedTabs] = useState<Set<string>>(new Set());

  const storeMap = useMemo<Record<string, string>>(
    () => Object.fromEntries(stores.map((s) => [s.store_id, s.store_name || s.store_id])),
    [stores],
  );

  const totalWalkins = useMemo(() => summaryRows.reduce((s, r) => s + Number(r.walkins || 0), 0), [summaryRows]);
  const totalConversions = useMemo(() => summaryRows.reduce((s, r) => s + Number(r.conversions || 0), 0), [summaryRows]);
  const avgRate = useMemo(
    () => summaryRows.length ? summaryRows.reduce((s, r) => s + Number(r.conversion_rate || 0), 0) / summaryRows.length : 0,
    [summaryRows],
  );
  const todayTag = new Date().toISOString().slice(0, 10);
  const tag = selectedStore || "all";

  const setTabRows = useCallback((view: string, rows: any[]) => {
    switch (view) {
      case "summary":
        setSummaryRows(rows);
        break;
      case "walkins":
        setWalkinRows(rows);
        break;
      case "image_scans":
        setScanRows(rows);
        break;
      case "validation":
        setValidationRows(rows);
        break;
    }
  }, []);

  const fetchTab = useCallback(async (view: string, sid: string | undefined, force = false) => {
    const key = cacheKey(sid ?? "all", view);
    if (!force) {
      const cached = readCache(key);
      if (cached) {
        setTabRows(view, cached);
        setFetchedTabs((prev) => new Set([...prev, view]));
        return;
      }
    }
    setLoading(true);
    try {
      let rows: any[] = [];
      switch (view) {
        case "summary":
          rows = (await reportsSummary(sid, 180)).data;
          break;
        case "walkins":
          rows = (await reportsWalkins(sid, undefined, 2000)).data;
          break;
        case "image_scans":
          rows = (await reportsImageScans(sid, undefined, 100000)).data;
          break;
        case "validation":
          rows = (await reportsValidationMap(sid, undefined, 5000)).data;
          break;
      }
      setTabRows(view, rows);
      writeCache(key, rows);
      setFetchedTabs((prev) => new Set([...prev, view]));
    } finally {
      setLoading(false);
    }
  }, [setTabRows]);

  const prevStoreRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (prevStoreRef.current === selectedStore) return;
    prevStoreRef.current = selectedStore;
    setSummaryRows([]);
    setWalkinRows([]);
    setScanRows([]);
    setValidationRows([]);
    setFetchedTabs(new Set());
    setPage(0);
  }, [selectedStore]);

  const prevScanFacilityRef = useRef<string>("");
  useEffect(() => {
    if (prevScanFacilityRef.current === scanFacility) return;
    prevScanFacilityRef.current = scanFacility;
    setScanRows([]);
    setFetchedTabs((prev) => {
      const next = new Set(prev);
      next.delete("image_scans");
      return next;
    });
  }, [scanFacility]);

  useEffect(() => {
    if (!fetchedTabs.has(reportView)) {
      const sid = reportView === "image_scans" ? (scanFacility || undefined) : (selectedStore || undefined);
      void fetchTab(reportView, sid);
    }
  }, [reportView, fetchedTabs, fetchTab, selectedStore, scanFacility]);

  useEffect(() => {
    if (!selectedStore) {
      setLiveProgress(null);
      return;
    }
    onFlyLiveProgress(selectedStore).then(({ data }) => setLiveProgress(data)).catch(() => setLiveProgress(null));
  }, [selectedStore]);

  useEffect(() => {
    setReportView(reportBucket === "main" ? "summary" : "image_scans");
  }, [reportBucket]);

  useEffect(() => {
    setPage(0);
  }, [reportView]);

  const reportChoices = reportBucket === "main"
    ? [{ value: "summary", label: "Store Summary" }, { value: "walkins", label: "Footfall Detail" }]
    : [{ value: "image_scans", label: "Image Scan Results" }, { value: "validation", label: "Footfall Analysis Validation" }];

  const activeRows = useMemo(() => {
    switch (reportView) {
      case "summary": return summaryRows;
      case "walkins": return walkinRows;
      case "image_scans": return scanRows;
      case "validation": return validationRows;
      default: return [];
    }
  }, [reportView, summaryRows, walkinRows, scanRows, validationRows]);

  const totalPages = Math.ceil(activeRows.length / pageSize);
  const visibleReportRows = activeRows.slice(page * pageSize, (page + 1) * pageSize);

  async function refreshReportData() {
    const sid = reportView === "image_scans" ? (scanFacility || undefined) : (selectedStore || undefined);
    await fetchTab(reportView, sid, true);
    if (selectedStore) {
      try {
        const { data } = await onFlyLiveProgress(selectedStore);
        setLiveProgress(data);
      } catch {
        setLiveProgress(null);
      }
    }
  }

  async function startExport(exportType: string) {
    if (exportingTab) return;
    setExportingTab(exportType);
    const toastId = Date.now();
    setToasts((prev) => [...prev, { id: toastId, msg: "Preparing download…", type: "loading" }]);
    try {
      const { data: job } = await reportsExportStart(exportType, selectedStore || undefined);
      const jobId = job.job_id;
      for (let i = 0; i < 60; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const { data: status } = await reportsExportStatus(jobId);
        if (status.status === "ready") {
          const { data: blob } = await reportsExportDownload(jobId);
          triggerDownload(status.filename || `${exportType}_${tag}_${todayTag}.csv`, blob as Blob);
          setToasts((prev) => prev.map((t) => (t.id === toastId ? { ...t, msg: "Download ready!", type: "success" } : t)));
          setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== toastId)), 3000);
          return;
        }
        if (status.status === "failed") throw new Error(status.error || "Export failed");
      }
      throw new Error("Export timed out after 60 seconds");
    } catch (err: any) {
      setToasts((prev) => prev.map((t) => (t.id === toastId ? { ...t, msg: err?.message || "Export failed", type: "error" } : t)));
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== toastId)), 5000);
    } finally {
      setExportingTab(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <Title>Management Reports</Title>
          <Text>Daily summary, footfall detail, and validation cross-reference from the live pipeline.</Text>
          {selectedStore && liveProgress && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <Badge color={liveProgress.is_running ? "amber" : liveProgress.status === "failed" ? "rose" : "emerald"}>
                {liveProgress.is_running ? `Sync Running: ${liveProgress.stage || "running"}` : liveProgress.status || "idle"}
              </Badge>
              {liveProgress.images_discovered ? <span className="text-slate-400">{liveProgress.images_processed || 0} / {liveProgress.images_discovered} processed</span> : null}
              {liveProgress.is_running ? <span className="text-slate-400">Report tables stay stable. Click Refresh Report Data when you want the latest snapshot.</span> : null}
              {liveProgress.is_running && liveProgress.error ? <span className="text-rose-500 truncate max-w-[18rem]">{liveProgress.error}</span> : null}
            </div>
          )}
        </div>
        <div className="w-full sm:w-80 flex flex-col gap-2">
          <button type="button" onClick={() => void refreshReportData()} className="iris-btn-secondary justify-center">
            <RefreshCw size={14} />
            Refresh Report Data
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card decoration="top" decorationColor="blue"><Text>Total Walk-ins In View</Text><Metric>{loading ? "—" : totalWalkins.toLocaleString()}</Metric></Card>
        <Card decoration="top" decorationColor="emerald"><Text>Total Conversions In View</Text><Metric>{loading ? "—" : totalConversions.toLocaleString()}</Metric></Card>
        <Card decoration="top" decorationColor="amber"><Text>Average Conversion Rate</Text><Metric>{loading ? "—" : `${(avgRate * 100).toFixed(1)}%`}</Metric></Card>
      </div>

      <Card className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="iris-label">Report Stack</label>
            <select className="iris-select" title="Report Stack" value={reportBucket} onChange={(e) => setReportBucket(e.target.value as "main" | "validation")}>
              <option value="main">Main Reports</option>
              <option value="validation">Validation Reports</option>
            </select>
          </div>
          <div>
            <label className="iris-label">Report View</label>
            <select className="iris-select" title="Report View" value={reportView} onChange={(e) => setReportView(e.target.value)}>
              {reportChoices.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
          {reportView === "image_scans" ? (
            <div>
              <label className="iris-label">Facility</label>
              <select className="iris-select" title="Facility Filter" value={scanFacility} onChange={(e) => setScanFacility(e.target.value)}>
                <option value="">All Facilities</option>
                {stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name || s.store_id}</option>)}
              </select>
            </div>
          ) : (
            <div>
              <label className="iris-label">Rows Per Page</label>
              <select className="iris-select" title="Rows Per Page" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}>
                <option value={10}>10 rows</option>
                <option value={20}>20 rows</option>
                <option value={50}>50 rows</option>
                <option value={100}>100 rows</option>
              </select>
            </div>
          )}
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-700">{reportChoices.find((option) => option.value === reportView)?.label || "Report"}</p>
            <p className="text-xs text-slate-400">
              {reportView === "validation"
                ? `${validationRows.length.toLocaleString()} rows — scrollable, virtualized.`
                : reportView === "image_scans"
                  ? `${scanRows.length.toLocaleString()} images — scrollable, virtualized.`
                  : activeRows.length > 0
                    ? `${page * pageSize + 1}–${Math.min((page + 1) * pageSize, activeRows.length)} of ${activeRows.length.toLocaleString()} rows`
                    : loading ? "Loading…" : "No data"}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {reportView !== "validation" && reportView !== "image_scans" && activeRows.length > pageSize && (
              <div className="flex items-center gap-1 text-sm">
                <button type="button" disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50 text-xs">← Prev</button>
                <span className="text-xs text-slate-500 px-1">Page {page + 1} / {totalPages}</span>
                <button type="button" disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)} className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50 text-xs">Next →</button>
              </div>
            )}
            <DownloadBtn label="Download CSV" loading={exportingTab === reportView} onClick={() => void startExport(reportView)} />
          </div>
        </div>

        {reportView === "validation" && (
          <Card className="p-4 bg-blue-50 border-blue-100">
            <p className="text-sm text-blue-800 font-medium">Walk-in ID → Source Image Cross-Reference</p>
            <p className="text-xs text-blue-600 mt-1">Each row shows a walk-in session alongside the exact image it was extracted from — including YOLO person count and GPT analysis results for that image. Use this to verify that the AI's conclusions match what the image actually shows.</p>
          </Card>
        )}
        {reportView === "image_scans" && (
          <Card className="p-4 bg-slate-50 border-slate-100">
            <p className="text-sm text-slate-800 font-medium">How to Read Image Scan Results</p>
            <p className="text-xs text-slate-600 mt-1">Every image the pipeline has ever scanned appears here — including rejected ones. <strong>Scan Status</strong> is the raw pipeline outcome. <strong> Rejection Reason</strong> explains in plain English why an image was not fully analysed: <em>"No people detected"</em> means YOLO found no one; <em>"Camera type excluded"</em> means external/backroom cameras are intentionally skipped; <em>"Outside store hours"</em> means the image was captured before open or after close; <em>"Duplicate image (skipped)"</em> means the same photo appeared twice. Rows marked <strong>Processed</strong> (green) contributed to footfall counts. Rows marked <strong>GPT cached (duplicate)</strong> (blue) reused an earlier result at zero GPT cost. Use the <strong>Facility</strong> dropdown above to narrow down to a single store.</p>
          </Card>
        )}
        {reportView === "walkins" && (
          <Card className="p-4 bg-amber-50 border-amber-100">
            <p className="text-sm text-amber-900 font-medium">How Footfall Detail Is Prepared</p>
            <p className="text-xs text-amber-700 mt-1">One row = one walk-in session from <code>onfly_walkin_sessions</code>. Entry/exit/dwell come from session logic. Source image fields are enriched from Drive image scans for the same store/date by preferring the session's direct source image, then matching images captured inside the session window. If the row shows <strong>Seeded Data = Yes</strong>, it is demo data and not a live GPT session.</p>
          </Card>
        )}

        <Card className="p-0 overflow-hidden">
          {loading ? <div className="p-8 text-center text-gray-400 text-sm">Loading…</div> : null}
          {!loading && reportView === "summary" ? <DaySummaryTable rows={visibleReportRows} storeMap={storeMap} /> : null}
          {!loading && reportView === "walkins" ? <WalkinTable rows={visibleReportRows} storeMap={storeMap} /> : null}
          {!loading && reportView === "image_scans" ? <ImageScanTable rows={scanRows} storeMap={storeMap} /> : null}
          {!loading && reportView === "validation" ? <ValidationTable rows={validationRows} storeMap={storeMap} /> : null}
        </Card>
      </Card>
      <ToastStack toasts={toasts} />
    </div>
  );
}
