import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Badge } from "@tremor/react";
import { Download } from "lucide-react";

export type ToastItem = { id: number; msg: string; type: "loading" | "success" | "error" };

export const CACHE_TTL_MS = 5 * 60 * 1000;

export function cacheKey(store: string, tab: string) {
  return `rp-v1:${store}:${tab}`;
}

export function readCache(key: string): any[] | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { rows: any[]; ts: number };
    if (Date.now() - parsed.ts > CACHE_TTL_MS) return null;
    return parsed.rows;
  } catch {
    return null;
  }
}

export function writeCache(key: string, rows: any[]) {
  try {
    sessionStorage.setItem(key, JSON.stringify({ rows, ts: Date.now() }));
  } catch {
    // sessionStorage quota exceeded — ignore and keep runtime state only.
  }
}

export function triggerDownload(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function DownloadBtn({ label, onClick, loading }: { label: string; onClick: () => void; loading?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition disabled:opacity-50 disabled:cursor-wait"
    >
      <Download size={13} className={loading ? "animate-bounce" : ""} />
      {loading ? "Preparing…" : label}
    </button>
  );
}

export function ToastStack({ toasts }: { toasts: ToastItem[] }) {
  if (!toasts.length) return null;
  return (
    <div className="fixed bottom-6 right-6 z-[500] flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-2.5 px-4 py-3 rounded-xl shadow-xl text-sm font-medium text-white transition-all ${
            t.type === "loading" ? "bg-blue-600" : t.type === "success" ? "bg-emerald-600" : "bg-rose-600"
          }`}
        >
          {t.type === "loading" && <Download size={14} className="animate-bounce shrink-0" />}
          {t.type === "success" && <Download size={14} className="shrink-0" />}
          {t.type === "error" && <span className="shrink-0 font-bold">!</span>}
          {t.msg}
        </div>
      ))}
    </div>
  );
}

export function DaySummaryTable({ rows, storeMap }: { rows: any[]; storeMap: Record<string, string> }) {
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
          {rows.length === 0 && <tr><td colSpan={7} className="px-5 py-10 text-center text-gray-400 text-sm">No summary data available.</td></tr>}
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

export function WalkinTable({ rows, storeMap }: { rows: any[]; storeMap: Record<string, string> }) {
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
              <td className="px-4 py-2.5 font-medium text-slate-700 sticky left-0 bg-white z-10 border-r border-slate-100">{storeMap[r.store_id] || r.store_id || "—"}</td>
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

function scanStatusColor(yoloStatus: string, gptStatus: string): "emerald" | "blue" | "amber" | "purple" | "rose" | "slate" {
  if (yoloStatus === "done" && gptStatus === "done") return "emerald";
  if (gptStatus === "cached_from_hash") return "blue";
  if (yoloStatus === "camera_excluded") return "amber";
  if (yoloStatus === "outside_hours") return "purple";
  if (yoloStatus === "failed_download" || gptStatus === "failed") return "rose";
  return "slate";
}

function rejectionColor(reason: string): "emerald" | "blue" | "amber" | "purple" | "rose" | "slate" {
  if (reason === "Processed") return "emerald";
  if (reason === "GPT cached (duplicate)") return "blue";
  if (reason === "Camera type excluded") return "amber";
  if (reason === "Outside store hours") return "purple";
  if (reason === "Download failed" || reason === "GPT analysis failed") return "rose";
  return "slate";
}

export function ImageScanTable({ rows, storeMap }: { rows: any[]; storeMap: Record<string, string> }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({ count: rows.length, getScrollElement: () => parentRef.current, estimateSize: () => 38, overscan: 10 });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0]?.start ?? 0 : 0;
  const paddingBottom = virtualRows.length > 0 ? rowVirtualizer.getTotalSize() - (virtualRows[virtualRows.length - 1]?.end ?? 0) : 0;
  const totalCols = 12;

  return (
    <div ref={parentRef} className="overflow-auto" style={{ height: rows.length > 20 ? "600px" : undefined, maxHeight: "600px" }}>
      <table className="w-full text-sm text-left whitespace-nowrap">
        <thead className="sticky top-0 z-20">
          <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
            <th className="px-4 py-3 sticky left-0 bg-slate-50 z-10">Store</th>
            <th className="px-4 py-3">Image</th>
            <th className="px-4 py-3">Date</th>
            <th className="px-4 py-3">Camera</th>
            <th className="px-4 py-3">Time</th>
            <th className="px-4 py-3">Scan Status</th>
            <th className="px-4 py-3">People</th>
            <th className="px-4 py-3">Rejection Reason</th>
            <th className="px-4 py-3">GPT</th>
            <th className="px-4 py-3">Customers</th>
            <th className="px-4 py-3">Staff</th>
            <th className="px-4 py-3">Error</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={totalCols} className="px-5 py-10 text-center text-gray-400 text-sm">No image scan results found.</td></tr>}
          {paddingTop > 0 && <tr><td colSpan={totalCols} style={{ height: paddingTop }} /></tr>}
          {virtualRows.map((virtualRow) => {
            const r = rows[virtualRow.index];
            const yoloStatus = String(r.yolo_status || "");
            const gptStatus = String(r.gpt_status || "");
            const rejReason = String(r.rejection_reason || "");
            const captureTime = String(r.capture_time || "").slice(11, 19) || "—";
            const errText = String(r.error_detail || r.yolo_error || r.gpt_error || "");
            return (
              <tr key={virtualRow.key} data-index={virtualRow.index} ref={rowVirtualizer.measureElement} className="border-b border-slate-100 hover:bg-slate-50/50">
                <td className="px-4 py-2.5 font-medium text-slate-700 sticky left-0 bg-white z-10 border-r border-slate-100">{storeMap[r.store_id] || r.store_id || "—"}</td>
                <td className="px-4 py-2.5 max-w-[180px] truncate font-mono text-xs text-slate-600" title={r.image_name}>{r.image_name || "—"}</td>
                <td className="px-4 py-2.5 text-slate-700">{r.business_date || "—"}</td>
                <td className="px-4 py-2.5 text-slate-700">{r.camera_id || "—"}</td>
                <td className="px-4 py-2.5 text-slate-600 font-mono text-xs">{captureTime}</td>
                <td className="px-4 py-2.5"><Badge color={scanStatusColor(yoloStatus, gptStatus)}>{yoloStatus || "pending"}</Badge></td>
                <td className="px-4 py-2.5 text-slate-700">{r.person_count}</td>
                <td className="px-4 py-2.5">{rejReason ? <Badge color={rejectionColor(rejReason)}>{rejReason}</Badge> : "—"}</td>
                <td className="px-4 py-2.5"><Badge color={gptStatus === "done" ? "emerald" : gptStatus === "cached_from_hash" ? "blue" : gptStatus === "failed" ? "rose" : "slate"}>{gptStatus || "—"}</Badge></td>
                <td className="px-4 py-2.5 text-slate-700">{r.customer_count}</td>
                <td className="px-4 py-2.5 text-slate-700">{r.staff_count}</td>
                <td className="px-4 py-2.5 max-w-[180px] truncate text-xs text-rose-500" title={errText}>{errText || ""}</td>
              </tr>
            );
          })}
          {paddingBottom > 0 && <tr><td colSpan={totalCols} style={{ height: paddingBottom }} /></tr>}
        </tbody>
      </table>
    </div>
  );
}

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

export function ValidationTable({ rows, storeMap }: { rows: any[]; storeMap: Record<string, string> }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({ count: rows.length, getScrollElement: () => parentRef.current, estimateSize: () => 38, overscan: 8 });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0]?.start ?? 0 : 0;
  const paddingBottom = virtualRows.length > 0 ? rowVirtualizer.getTotalSize() - (virtualRows[virtualRows.length - 1]?.end ?? 0) : 0;
  const totalCols = SESSION_COLS.length + IMAGE_COLS.length + 2;

  return (
    <div ref={parentRef} className="overflow-auto" style={{ height: rows.length > 20 ? "600px" : undefined, maxHeight: "600px" }}>
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
          {rows.length === 0 && <tr><td colSpan={totalCols} className="px-5 py-10 text-center text-gray-400 text-sm">No validation data found.</td></tr>}
          {paddingTop > 0 && <tr><td colSpan={totalCols} style={{ height: paddingTop }} /></tr>}
          {virtualRows.map((virtualRow) => {
            const r = rows[virtualRow.index];
            const hasImage = r["Image Filename"] && r["Image Filename"] !== "—";
            return (
              <tr key={virtualRow.key} data-index={virtualRow.index} ref={rowVirtualizer.measureElement} className={`border-b border-slate-100 hover:bg-slate-50/50 ${hasImage ? "" : "opacity-60"}`}>
                <td className="px-4 py-2.5 font-medium text-slate-700 sticky left-0 bg-white z-10 border-r border-slate-100">{storeMap[r.store_id] || r.store_id || "—"}</td>
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
                  if (c.key === "Drive Link") return <td key={c.key} className="px-4 py-2.5 bg-emerald-50/30">{val && val !== "—" ? <a href={val} target="_blank" rel="noreferrer" className="text-blue-600 hover:text-blue-800 underline text-xs">Open ↗</a> : <span className="text-slate-300 text-xs">no link</span>}</td>;
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
