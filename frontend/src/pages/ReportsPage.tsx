import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  reportsSummary,
  reportsWalkins,
  reportsImageScans,
  reportsValidationMap,
  reportsDownloadSummary,
  reportsDownloadWalkins,
  reportsDownloadImageScans,
  reportsDownloadValidationMap,
  adminListStores,
  onFlyLiveProgress,
} from "../api/client";
import { Card, Title, Text, Badge, Metric } from "@tremor/react";
import StoreSelect from "../components/StoreSelect";
import { Download, RefreshCw } from "lucide-react";

// ── Download helpers ──────────────────────────────────────────────────────────

function triggerDownload(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function toCSV(rows: any[], cols?: string[]): string {
  if (!rows.length) return "";
  const keys = cols ?? Object.keys(rows[0]);
  const escape = (v: any) => {
    const s = String(v ?? "");
    return s.includes(",") || s.includes('"') || s.includes("\n")
      ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [keys.join(","), ...rows.map((r) => keys.map((k) => escape(r[k])).join(","))].join("\n");
}

function csvFallback(filename: string, rows: any[], cols?: string[]) {
  triggerDownload(filename, new Blob([toCSV(rows, cols)], { type: "text/csv;charset=utf-8;" }));
}

function DownloadBtn({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition"
    >
      <Download size={13} />
      {label}
    </button>
  );
}

// ── Tables ────────────────────────────────────────────────────────────────────

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
            <tr><td colSpan={7} className="px-5 py-10 text-center text-gray-400 text-sm">No summary data available.</td></tr>
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
  { key: "Source Image", label: "Source Image" },
  { key: "Drive Actual Image Name", label: "Drive Image Name" },
  { key: "Drive Folder Name", label: "Drive Folder" },
  { key: "Drive Image Link", label: "Drive Link" },
  { key: "Seeded Data", label: "Seeded Data" },
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
            {WALKIN_COLS.map((c) => <th key={c.key} className="px-4 py-3">{c.label}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={r.id ?? i} className="hover:bg-slate-50/50">
              <td className="px-4 py-2.5 font-medium text-slate-700 sticky left-0 bg-white z-10 border-r border-slate-100">
                {storeMap[r.store_id] || r.store_id || "—"}
              </td>
              {WALKIN_COLS.map((c) => {
                const val = r[c.key] ?? "";
                if (c.key === "Role") return <td key={c.key} className="px-4 py-2.5"><Badge color={roleBadgeColor(String(val))}>{String(val) || "—"}</Badge></td>;
                if (c.key === "Session Status") return <td key={c.key} className="px-4 py-2.5"><Badge color={String(val).toUpperCase() === "CLOSED" ? "slate" : "amber"}>{String(val) || "—"}</Badge></td>;
                if (c.key === "Included in Analytics") return <td key={c.key} className="px-4 py-2.5"><Badge color={String(val).toLowerCase() === "yes" ? "emerald" : "rose"}>{String(val) || "—"}</Badge></td>;
                if (c.key === "Purchase Signal (Bag)") return <td key={c.key} className="px-4 py-2.5"><Badge color={String(val).toLowerCase() === "yes" ? "emerald" : "slate"}>{String(val) || "—"}</Badge></td>;
                if (c.key === "Seeded Data") return <td key={c.key} className="px-4 py-2.5"><Badge color={String(val).toLowerCase() === "yes" ? "amber" : "slate"}>{String(val) || "—"}</Badge></td>;
                if (c.key === "Drive Image Link") return <td key={c.key} className="px-4 py-2.5">{String(val) ? <a href={String(val)} target="_blank" rel="noreferrer" className="text-blue-600 hover:text-blue-800 underline text-xs">Open ↗</a> : "—"}</td>;
                if (c.key === "Attire / Visual Marker") return <td key={c.key} className="px-4 py-2.5 max-w-[180px] truncate text-slate-600 text-xs" title={String(val)}>{String(val) || "—"}</td>;
                if (c.key === "Source Image" || c.key === "Drive Actual Image Name" || c.key === "Drive Folder Name") return <td key={c.key} className="px-4 py-2.5 max-w-[180px] truncate font-mono text-xs text-slate-600" title={String(val)}>{String(val) || "—"}</td>;
                return <td key={c.key} className="px-4 py-2.5 text-slate-700">{String(val) || "—"}</td>;
              })}
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={WALKIN_COLS.length + 1} className="px-5 py-10 text-center text-gray-400 text-sm">No walk-in sessions found.</td></tr>}
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
            <th className="px-5 py-3">People</th>
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
              <td className="px-5 py-3"><Badge color={r.yolo_relevant ? "emerald" : "slate"}>{r.yolo_relevant ? "Relevant" : "Skip"}</Badge></td>
              <td className="px-5 py-3">{r.person_count}</td>
              <td className="px-5 py-3"><Badge color={r.gpt_status === "done" ? "emerald" : r.gpt_status === "failed" ? "rose" : "slate"}>{r.gpt_status || "—"}</Badge></td>
              <td className="px-5 py-3">{r.customer_count}</td>
              <td className="px-5 py-3">{r.staff_count}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={9} className="px-5 py-10 text-center text-gray-400 text-sm">No image scan results found.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// Session columns (left side — one per walk-in)
const SESSION_COLS = [
  { key: "Date", label: "Date" },
  { key: "Walk-in ID", label: "Walk-in ID" },
  { key: "Group ID", label: "Group ID" },
  { key: "Role", label: "Role" },
  { key: "Gender", label: "Gender" },
  { key: "Age Band", label: "Age Band" },
  { key: "Entry Time", label: "Entry" },
  { key: "Exit Time", label: "Exit" },
  { key: "Dwell (mins)", label: "Dwell" },
  { key: "In Analytics", label: "Analytics" },
  { key: "Purchase Signal", label: "Purchase" },
  { key: "Session Camera", label: "Session Cam" },
  { key: "Session Source Image", label: "Source Image" },
  { key: "Session Drive Folder", label: "Drive Folder" },
  { key: "Seeded Data", label: "Seeded" },
];

// Image columns (right side — multiple per walk-in when window images found)
const IMAGE_COLS = [
  { key: "Image Filename", label: "Image File" },
  { key: "Drive Folder", label: "Img Folder" },
  { key: "Image Camera", label: "Img Camera" },
  { key: "Camera Match", label: "Match Type" },
  { key: "Image Time", label: "Img Time" },
  { key: "YOLO Relevant", label: "YOLO" },
  { key: "YOLO People", label: "People" },
  { key: "GPT Customers", label: "GPT Cust." },
  { key: "GPT Staff", label: "GPT Staff" },
  { key: "GPT Status", label: "GPT" },
  { key: "Drive Link", label: "Open Image" },
];

function ValidationTable({ rows, storeMap }: { rows: any[]; storeMap: Record<string, string> }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const totalCols = SESSION_COLS.length + IMAGE_COLS.length + 2; // +2: Store col + divider col

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 38,
    overscan: 8,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualRows.length > 0 ? (virtualRows[0]?.start ?? 0) : 0;
  const paddingBottom = virtualRows.length > 0
    ? rowVirtualizer.getTotalSize() - (virtualRows[virtualRows.length - 1]?.end ?? 0)
    : 0;

  return (
    <div
      ref={parentRef}
      className="overflow-auto"
      style={{ height: rows.length > 20 ? "600px" : undefined, maxHeight: "600px" }}
    >
      <table className="w-full text-sm text-left whitespace-nowrap">
        <thead className="sticky top-0 z-20">
          <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
            <th className="px-4 py-3 sticky left-0 bg-slate-50 z-10">Store</th>
            {SESSION_COLS.map((c) => <th key={c.key} className="px-4 py-3 bg-blue-50">{c.label}</th>)}
            <th className="px-2 py-3 bg-slate-100 text-slate-300">│</th>
            {IMAGE_COLS.map((c) => <th key={c.key} className="px-4 py-3 bg-emerald-50">{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={totalCols} className="px-5 py-10 text-center text-gray-400 text-sm">No validation data found.</td></tr>
          )}
          {paddingTop > 0 && <tr><td colSpan={totalCols} style={{ height: paddingTop }} /></tr>}
          {virtualRows.map((virtualRow) => {
            const r = rows[virtualRow.index];
            const hasImage = r["Image Filename"] && r["Image Filename"] !== "—";
            return (
              <tr
                key={virtualRow.key}
                data-index={virtualRow.index}
                ref={rowVirtualizer.measureElement}
                className={`border-b border-slate-100 hover:bg-slate-50/50 ${hasImage ? "" : "opacity-60"}`}
              >
                <td className="px-4 py-2.5 font-medium text-slate-700 sticky left-0 bg-white z-10 border-r border-slate-100">
                  {storeMap[r.store_id] || r.store_id || "—"}
                </td>
                {SESSION_COLS.map((c) => {
                  const val = String(r[c.key] ?? "");
                  if (c.key === "Role") return <td key={c.key} className="px-4 py-2.5 bg-blue-50/30"><Badge color={roleBadgeColor(val)}>{val || "—"}</Badge></td>;
                  if (c.key === "In Analytics") return <td key={c.key} className="px-4 py-2.5 bg-blue-50/30"><Badge color={val.toLowerCase() === "yes" ? "emerald" : "rose"}>{val || "—"}</Badge></td>;
                  if (c.key === "Purchase Signal") return <td key={c.key} className="px-4 py-2.5 bg-blue-50/30"><Badge color={val.toLowerCase() === "yes" ? "emerald" : "slate"}>{val || "—"}</Badge></td>;
                  if (c.key === "Seeded Data") return <td key={c.key} className="px-4 py-2.5 bg-blue-50/30"><Badge color={val === "Yes" ? "amber" : "slate"}>{val === "Yes" ? "Seeded" : "Live"}</Badge></td>;
                  if (c.key === "Session Source Image") return <td key={c.key} className="px-4 py-2.5 bg-blue-50/30 max-w-[140px] truncate font-mono text-xs text-slate-600" title={val}>{val || "—"}</td>;
                  return <td key={c.key} className="px-4 py-2.5 bg-blue-50/30 text-slate-700">{val || "—"}</td>;
                })}
                <td className="px-2 bg-slate-100 text-slate-300">│</td>
                {IMAGE_COLS.map((c) => {
                  const val = String(r[c.key] ?? "");
                  if (c.key === "Drive Link") return (
                    <td key={c.key} className="px-4 py-2.5 bg-emerald-50/30">
                      {val && val !== "—" && val !== "" ? (
                        <a href={val} target="_blank" rel="noreferrer"
                           className="text-blue-600 hover:text-blue-800 underline text-xs">Open ↗</a>
                      ) : <span className="text-slate-300 text-xs">no link</span>}
                    </td>
                  );
                  if (c.key === "Camera Match") {
                    const isExact = val === "Exact" || val === "Direct name match";
                    const isCross = val.startsWith("Cross-camera");
                    const color = isExact ? "emerald" : isCross ? "rose" : "slate";
                    return <td key={c.key} className="px-4 py-2.5 bg-emerald-50/30 max-w-[200px]" title={val}><Badge color={color}>{isExact ? val : isCross ? "⚠ Cross-camera" : val}</Badge></td>;
                  }
                  if (c.key === "YOLO Relevant") return <td key={c.key} className="px-4 py-2.5 bg-emerald-50/30"><Badge color={val === "Yes" ? "emerald" : "slate"}>{val}</Badge></td>;
                  if (c.key === "GPT Status") return <td key={c.key} className="px-4 py-2.5 bg-emerald-50/30"><Badge color={val === "done" ? "emerald" : val === "failed" ? "rose" : "slate"}>{val}</Badge></td>;
                  if (c.key === "Image Filename") return <td key={c.key} className="px-4 py-2.5 bg-emerald-50/30 max-w-[160px] truncate font-mono text-xs text-slate-600" title={val}>{val}</td>;
                  return <td key={c.key} className="px-4 py-2.5 bg-emerald-50/30 text-slate-700">{val}</td>;
                })}
              </tr>
            );
          })}
          {paddingBottom > 0 && <tr><td colSpan={totalCols} style={{ height: paddingBottom }} /></tr>}
        </tbody>
      </table>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ReportsPage() {
  const [stores, setStores] = useState<any[]>([]);
  const [selectedStore, setSelectedStore] = useState("");
  const [reportBucket, setReportBucket] = useState<"main" | "validation">("main");
  const [reportView, setReportView] = useState("summary");
  const [visibleRows, setVisibleRows] = useState(10);
  const [summaryRows, setSummaryRows] = useState<any[]>([]);
  const [walkinRows, setWalkinRows] = useState<any[]>([]);
  const [scanRows, setScanRows] = useState<any[]>([]);
  const [validationRows, setValidationRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [liveProgress, setLiveProgress] = useState<any>(null);

  const storeMap = useMemo(
    () => Object.fromEntries(stores.map((s) => [s.store_id, s.store_name || s.store_id])),
    [stores],
  );
  const totalWalkins = useMemo(
    () => summaryRows.reduce((s, r) => s + Number(r.walkins || 0), 0),
    [summaryRows],
  );
  const totalConversions = useMemo(
    () => summaryRows.reduce((s, r) => s + Number(r.conversions || 0), 0),
    [summaryRows],
  );
  const avgRate = useMemo(
    () => summaryRows.length
      ? summaryRows.reduce((s, r) => s + Number(r.conversion_rate || 0), 0) / summaryRows.length
      : 0,
    [summaryRows],
  );
  const todayTag = new Date().toISOString().slice(0, 10);
  const tag = selectedStore || "all";

  const loadReports = useCallback(() => {
    setLoading(true);
    const sid = selectedStore || undefined;
    return Promise.all([
      reportsSummary(sid, 180).then((r) => setSummaryRows(r.data)),
      reportsWalkins(sid, undefined, 2000).then((r) => setWalkinRows(r.data)),
      reportsImageScans(sid, undefined, 2000).then((r) => setScanRows(r.data)),
      reportsValidationMap(sid, undefined, 5000).then((r) => setValidationRows(r.data)),
    ]).finally(() => setLoading(false));
  }, [selectedStore]);

  useEffect(() => {
    adminListStores().then((r) => setStores(r.data));
  }, []);

  useEffect(() => {
    if (!selectedStore) return; // blank first — load only when a store is selected
    void loadReports();
  }, [loadReports, selectedStore]);

  useEffect(() => {
    if (!selectedStore) { setLiveProgress(null); return; }
    onFlyLiveProgress(selectedStore).then(({ data }) => setLiveProgress(data)).catch(() => setLiveProgress(null));
  }, [selectedStore]);

  useEffect(() => {
    setReportView(reportBucket === "main" ? "summary" : "image_scans");
  }, [reportBucket]);

  const reportChoices = reportBucket === "main"
    ? [
        { value: "summary", label: "Store Summary" },
        { value: "walkins", label: "Footfall Detail" },
      ]
    : [
        { value: "image_scans", label: "Image Scan Results" },
        { value: "validation", label: "Footfall Analysis Validation" },
      ];

  const activeRows = useMemo(() => {
    switch (reportView) {
      case "summary":
        return summaryRows;
      case "walkins":
        return walkinRows;
      case "image_scans":
        return scanRows;
      case "validation":
        return validationRows;
      default:
        return [];
    }
  }, [reportView, summaryRows, walkinRows, scanRows, validationRows]);

  const visibleReportRows = activeRows.slice(0, visibleRows);

  async function refreshReportData() {
    await loadReports();
    if (selectedStore) {
      try {
        const { data } = await onFlyLiveProgress(selectedStore);
        setLiveProgress(data);
      } catch {
        setLiveProgress(null);
      }
    }
  }

  function downloadSummary() {
    reportsDownloadSummary(selectedStore || undefined)
      .then(({ data }) => triggerDownload(`summary_${tag}_${todayTag}.csv`, data as Blob))
      .catch(() => csvFallback(`summary_${tag}_${todayTag}.csv`, summaryRows.map(r => ({
        Store: storeMap[r.store_id] || r.store_id,
        Date: r.business_date,
        "Walk-ins": r.walkins,
        Conversions: r.conversions,
        "Conv. Rate %": (r.conversion_rate * 100).toFixed(1),
        "Avg Dwell (mins)": r.avg_dwell_mins?.toFixed(1),
        "Relevant Images": r.relevant_images,
        "Raw Images": r.raw_images,
      }))));
  }

  function downloadWalkins() {
    reportsDownloadWalkins(selectedStore || undefined)
      .then(({ data }) => triggerDownload(`walkins_${tag}_${todayTag}.csv`, data as Blob))
      .catch(() => csvFallback(`walkins_${tag}_${todayTag}.csv`, walkinRows.map(r => ({
        Store: storeMap[r.store_id] || r.store_id,
        ...Object.fromEntries(WALKIN_COLS.map(c => [c.label, r[c.key] ?? ""])),
      }))));
  }

  function downloadScans() {
    reportsDownloadImageScans(selectedStore || undefined)
      .then(({ data }) => triggerDownload(`image_scans_${tag}_${todayTag}.csv`, data as Blob))
      .catch(() => csvFallback(`image_scans_${tag}_${todayTag}.csv`, scanRows.map(r => ({
        Store: storeMap[r.store_id] || r.store_id,
        Image: r.image_name, Date: r.business_date, Camera: r.camera_id || "",
        "YOLO Relevant": r.yolo_relevant ? "Yes" : "No",
        "Person Count": r.person_count, "GPT Status": r.gpt_status || "",
        Customers: r.customer_count, Staff: r.staff_count,
      }))));
  }

  function downloadValidation() {
    reportsDownloadValidationMap(selectedStore || undefined)
      .then(({ data }) => triggerDownload(`validation_${tag}_${todayTag}.csv`, data as Blob))
      .catch(() => csvFallback(`validation_${tag}_${todayTag}.csv`, validationRows.map(r => ({
        Store: storeMap[r.store_id] || r.store_id,
        ...Object.fromEntries([...SESSION_COLS, ...IMAGE_COLS].map((c: {key: string; label: string}) => [c.label, r[c.key] ?? ""])),
      }))));
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <Title>Management Reports</Title>
          <Text>Daily summary, footfall detail, and validation cross-reference from the live pipeline.</Text>
          {selectedStore && liveProgress && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <Badge color={liveProgress.is_running ? "amber" : liveProgress.status === "failed" ? "rose" : "emerald"}>
                {liveProgress.is_running ? `Sync Running: ${liveProgress.stage || "running"}` : liveProgress.status || "idle"}
              </Badge>
              {liveProgress.images_discovered ? (
                <span className="text-slate-400">{liveProgress.images_processed || 0} / {liveProgress.images_discovered} processed</span>
              ) : null}
              {liveProgress.is_running ? (
                <span className="text-slate-400">Report tables stay stable. Click Refresh Report Data when you want the latest snapshot.</span>
              ) : null}
              {liveProgress.error ? <span className="text-rose-500 truncate max-w-[18rem]">{liveProgress.error}</span> : null}
            </div>
          )}
        </div>
        <div className="w-full sm:w-80 flex flex-col gap-2">
          <StoreSelect stores={stores} value={selectedStore} onChange={setSelectedStore} includeAll allLabel="All Stores" placeholder="Filter reports by store" />
          <button onClick={() => void refreshReportData()} className="iris-btn-secondary justify-center">
            <RefreshCw size={14} />
            Refresh Report Data
          </button>
        </div>
      </div>

      {/* Empty state */}
      {!selectedStore && !loading && (
        <Card className="p-12 text-center space-y-2">
          <p className="text-slate-500 text-sm font-medium">Select a store to load report data.</p>
          <p className="text-slate-400 text-xs">Use the store selector above to choose a store and view walk-in reports, image scans, and validation data.</p>
        </Card>
      )}

      {/* KPI cards + report table (only shown when store selected) */}
      {selectedStore && <><div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
          <Metric>{loading ? "—" : `${(avgRate * 100).toFixed(1)}%`}</Metric>
        </Card>
      </div>

      <Card className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="iris-label">Report Stack</label>
            <select
              className="iris-select"
              value={reportBucket}
              onChange={(e) => setReportBucket(e.target.value as "main" | "validation")}
            >
              <option value="main">Main Reports</option>
              <option value="validation">Validation Reports</option>
            </select>
          </div>
          <div>
            <label className="iris-label">Report View</label>
            <select
              className="iris-select"
              value={reportView}
              onChange={(e) => setReportView(e.target.value)}
            >
              {reportChoices.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="iris-label">Rows In UI</label>
            <select
              className="iris-select"
              value={visibleRows}
              onChange={(e) => setVisibleRows(Number(e.target.value))}
            >
              <option value={10}>10 rows</option>
              <option value={100}>100 rows</option>
              <option value={500}>500 rows</option>
            </select>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-700">
              {reportChoices.find((option) => option.value === reportView)?.label || "Report"}
            </p>
            <p className="text-xs text-slate-400">
              {reportView === "validation"
                ? `${validationRows.length.toLocaleString()} rows — scrollable, virtualized. Download includes all.`
                : `Showing top ${Math.min(visibleRows, activeRows.length)} of ${activeRows.length.toLocaleString()} rows in UI. Download always includes all available rows.`}
            </p>
          </div>
          <div className="flex justify-end">
            {reportView === "summary" && <DownloadBtn label="Download CSV" onClick={downloadSummary} />}
            {reportView === "walkins" && <DownloadBtn label="Download CSV" onClick={downloadWalkins} />}
            {reportView === "image_scans" && <DownloadBtn label="Download CSV" onClick={downloadScans} />}
            {reportView === "validation" && <DownloadBtn label="Download CSV" onClick={downloadValidation} />}
          </div>
        </div>

        {reportView === "validation" && (
          <Card className="p-4 bg-blue-50 border-blue-100">
            <p className="text-sm text-blue-800 font-medium">Walk-in ID → Source Image Cross-Reference</p>
            <p className="text-xs text-blue-600 mt-1">
              Each row shows a walk-in session alongside the exact image it was extracted from — including YOLO person count and GPT analysis results for that image. Use this to verify that the AI's conclusions match what the image actually shows.
            </p>
          </Card>
        )}
        {reportView === "walkins" && (
          <Card className="p-4 bg-amber-50 border-amber-100">
            <p className="text-sm text-amber-900 font-medium">How Footfall Detail Is Prepared</p>
            <p className="text-xs text-amber-700 mt-1">
              One row = one walk-in session from <code>onfly_walkin_sessions</code>. Entry/exit/dwell come from session logic.
              Source image fields are enriched from Drive image scans for the same store/date by preferring the session's direct source image,
              then matching images captured inside the session window. If the row shows <strong>Seeded Data = Yes</strong>, it is demo data and not a live GPT session.
            </p>
          </Card>
        )}

        <Card className="p-0 overflow-hidden">
          {loading ? <div className="p-8 text-center text-gray-400 text-sm">Loading…</div> : null}
          {!loading && reportView === "summary" ? <DaySummaryTable rows={visibleReportRows} storeMap={storeMap} /> : null}
          {!loading && reportView === "walkins" ? <WalkinTable rows={visibleReportRows} storeMap={storeMap} /> : null}
          {!loading && reportView === "image_scans" ? <ImageScanTable rows={visibleReportRows} storeMap={storeMap} /> : null}
          {!loading && reportView === "validation" ? <ValidationTable rows={validationRows} storeMap={storeMap} /> : null}
        </Card>
      </Card>
      </> }
    </div>
  );
}
