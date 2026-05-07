import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  qaReviewQueue,
  qaCreateFeedback,
  qaUpdateFeedback,
  qaDeleteFeedback,
  qaFrameImageUrl,
  qaAnnotatedFrameImageUrl,
} from "../api/client";
import { Card, Title, Text, Badge } from "@tremor/react";
import {
  Check, X, Trash2, RefreshCw, ExternalLink,
  ChevronLeft, ChevronRight, Zap, Eye, Cpu, ScanSearch,
} from "lucide-react";
import { useStore } from "../context/StoreContext";

const LABELS = ["customer", "staff", "banner", "pedestrian", "unknown", "no_human"];
const PAGE_SIZE = 24;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 min

// ── SessionStorage cache helpers ──────────────────────────────────────────
function cacheKey(storeId: string, status: string, date: string) {
  return `fr-v2:${storeId}:${status}:${date}`;
}
function readCache(key: string): { rows: any[]; ts: number } | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { rows: any[]; ts: number };
    if (Date.now() - parsed.ts > CACHE_TTL_MS) return null;
    return parsed;
  } catch { return null; }
}
function writeCache(key: string, rows: any[]) {
  try { sessionStorage.setItem(key, JSON.stringify({ rows, ts: Date.now() })); } catch { /* quota */ }
}

// ── Hover preview portal ─────────────────────────────────────────────────
function HoverPreview({ src, rect }: { src: string; rect: DOMRect }) {
  const W = 320, H = 240, margin = 12;
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = rect.right + margin;
  let top = rect.top + rect.height / 2 - H / 2;
  if (left + W > vw - margin) left = rect.left - W - margin;
  if (top < margin) top = margin;
  if (top + H > vh - margin) top = vh - H - margin;
  return createPortal(
    <div
      className="fixed z-[9999] rounded-xl overflow-hidden shadow-2xl border-2 border-white pointer-events-none"
      style={{ left, top, width: W, height: H, boxShadow: "0 20px 60px rgba(0,0,0,0.35)" }}
    >
      <img src={src} alt="preview" className="w-full h-full object-cover" />
    </div>,
    document.body,
  );
}

function statusColor(s: string) {
  if (s === "confirmed") return "emerald";
  if (s === "rejected") return "rose";
  return "amber";
}

function predictedColor(label: string) {
  const n = (label || "").toLowerCase();
  if (n === "customer") return "emerald";
  if (n === "staff") return "blue";
  if (n === "banner") return "orange";
  if (n === "pedestrian") return "violet";
  return "slate";
}

// ── Step section header ──────────────────────────────────────────────────
function StepHeader({ icon, step, label, color }: { icon: React.ReactNode; step: string; label: string; color: string }) {
  return (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-semibold ${color}`}>
      {icon}
      <span className="uppercase tracking-wide opacity-70">{step}</span>
      <span>{label}</span>
    </div>
  );
}

function MetricPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md bg-slate-50 px-2 py-1 border border-slate-200 flex flex-col">
      <p className="text-[9px] uppercase tracking-wide text-slate-400 leading-tight">{label}</p>
      <p className="text-sm font-semibold text-slate-700">{value}</p>
    </div>
  );
}

// ── FeedbackCard ─────────────────────────────────────────────────────────
function FeedbackCard({
  row, onSaved, onDelete,
}: {
  row: any;
  onSaved: (updated: any) => void;
  onDelete: (imageId: string) => void;
}) {
  const [corrected, setCorrected] = useState(row.corrected_label || row.predicted_label || "");
  const [comment, setComment] = useState(row.comment || "");
  const [saving, setSaving] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [hoverRect, setHoverRect] = useState<DOMRect | null>(null);
  const [showAnnotated, setShowAnnotated] = useState(false);
  const thumbRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setCorrected(row.corrected_label || row.predicted_label || "");
    setComment(row.comment || "");
    setImgError(false);
  }, [row.image_id]);

  async function save(reviewStatus: "confirmed" | "rejected") {
    setSaving(true);
    try {
      if (row.feedback_id) {
        await qaUpdateFeedback(row.feedback_id, { review_status: reviewStatus, corrected_label: corrected, comment });
      } else {
        await qaCreateFeedback({
          store_id: row.store_id,
          capture_date: row.capture_date,
          filename: row.filename,
          camera_id: row.camera_id,
          track_id: "FRAME",
          predicted_label: row.predicted_label,
          corrected_label: corrected,
          confidence: row.confidence || 0.8,
          drive_link: row.drive_link || row.source_url || "",
          needs_review: true,
          review_status: reviewStatus,
          comment,
        });
      }
      onSaved({ ...row, review_status: reviewStatus, corrected_label: corrected, comment });
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!row.feedback_id) { onDelete(row.image_id); return; }
    if (!confirm("Delete this review row?")) return;
    await qaDeleteFeedback(row.feedback_id);
    onDelete(row.image_id);
  }

  const rawSrc = qaFrameImageUrl(row.store_id, row.image_id);
  const annSrc = qaAnnotatedFrameImageUrl(row.store_id, row.image_id);
  const imgSrc = showAnnotated ? annSrc : rawSrc;

  if (row.auto_approved) {
    return (
      <div className="border border-emerald-200 rounded-2xl bg-emerald-50/40 overflow-hidden">
        {hoverRect && !imgError && <HoverPreview src={imgSrc} rect={hoverRect} />}
        <div className="relative">
          <div
            ref={thumbRef}
            className="bg-slate-100 flex items-center justify-center h-36 overflow-hidden cursor-zoom-in"
            onMouseEnter={() => setHoverRect(thumbRef.current?.getBoundingClientRect() ?? null)}
            onMouseLeave={() => setHoverRect(null)}
          >
            {!imgError ? (
              <img src={imgSrc} alt={row.filename}
                className="object-cover h-full w-full hover:scale-105 transition-transform duration-200"
                loading="lazy" onError={() => setImgError(true)} />
            ) : (
              <div className="text-slate-400 text-xs text-center px-3">Thumbnail unavailable</div>
            )}
          </div>
          <button
            type="button"
            onClick={() => { setShowAnnotated((v) => !v); setImgError(false); }}
            title={showAnnotated ? "Show raw frame" : "Show ONNX detection boxes"}
            className={`absolute top-1.5 right-1.5 p-1 rounded-md text-xs font-medium shadow transition-colors ${showAnnotated ? "bg-blue-600 text-white" : "bg-white/80 text-slate-600 hover:bg-blue-50"}`}
          >
            <ScanSearch size={13} />
          </button>
        </div>
        <div className="p-3 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-xs font-mono text-slate-600 truncate">{row.filename || "—"}</p>
              <p className="text-xs text-slate-400">{row.capture_date_display || row.capture_date || "—"} · {row.camera_id || "—"}</p>
            </div>
            <Badge color="emerald" size="xs">confirmed</Badge>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-100 rounded-lg px-2.5 py-1.5">
            <Zap size={12} />
            <span>Auto-approved — 0 people detected by YOLO</span>
          </div>
        </div>
      </div>
    );
  }

  // YOLO confidence display
  const yoloConf = row.confidence ? `${Math.round(row.confidence * 100)}%` : "—";
  const isHighConf = (row.confidence || 0) >= 0.65;

  return (
    <div className={`border rounded-2xl bg-white overflow-hidden hover:shadow-md transition-shadow ${
      row.review_status === "confirmed" ? "border-emerald-200"
      : row.review_status === "rejected" ? "border-rose-200"
      : "border-slate-200"
    }`}>
      {hoverRect && !imgError && <HoverPreview src={imgSrc} rect={hoverRect} />}
      <div className="relative">
        <div
          ref={thumbRef}
          className="bg-slate-100 flex items-center justify-center h-36 overflow-hidden cursor-zoom-in"
          onMouseEnter={() => setHoverRect(thumbRef.current?.getBoundingClientRect() ?? null)}
          onMouseLeave={() => setHoverRect(null)}
        >
          {!imgError ? (
            <img src={imgSrc} alt={row.filename}
              className="object-cover h-full w-full hover:scale-105 transition-transform duration-200"
              loading="lazy" onError={() => setImgError(true)} />
          ) : (
            <div className="text-slate-400 text-xs text-center px-3">Thumbnail unavailable</div>
          )}
        </div>
        <button
          type="button"
          onClick={() => { setShowAnnotated((v) => !v); setImgError(false); }}
          title={showAnnotated ? "Show raw frame" : "Show ONNX detection boxes"}
          className={`absolute top-1.5 right-1.5 p-1 rounded-md shadow transition-colors ${showAnnotated ? "bg-blue-600 text-white" : "bg-white/80 text-slate-600 hover:bg-blue-50"}`}
        >
          <ScanSearch size={13} />
        </button>
      </div>

      <div className="p-3 space-y-2.5">
        {/* Filename + status */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-mono text-slate-600 truncate">{row.filename || "—"}</p>
            <p className="text-xs text-slate-400">{row.capture_date_display || row.capture_date || "—"} · {row.camera_id || "—"}</p>
          </div>
          <Badge color={statusColor(row.review_status || "pending")}>{row.review_status || "pending"}</Badge>
        </div>

        {/* Step 1 — YOLO */}
        <div className="rounded-lg border border-slate-200 overflow-hidden">
          <StepHeader
            icon={<Eye size={11} />}
            step="Step 1"
            label="YOLO Detection"
            color="bg-blue-50 text-blue-700 border-b border-blue-100"
          />
          <div className="grid grid-cols-2 gap-1.5 p-2">
            <MetricPill label="People" value={row.person_count ?? 0} />
            <MetricPill label="Confidence" value={yoloConf} />
          </div>
          {!isHighConf && (row.person_count ?? 0) > 0 && (
            <p className="text-[9px] text-amber-600 px-2 pb-1.5">Low YOLO confidence — may be banner or poster</p>
          )}
        </div>

        {/* Step 2 — GPT */}
        <div className="rounded-lg border border-slate-200 overflow-hidden">
          <StepHeader
            icon={<Cpu size={11} />}
            step="Step 2"
            label="GPT Classification"
            color="bg-purple-50 text-purple-700 border-b border-purple-100"
          />
          <div className="p-2 space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] text-slate-400">Label:</span>
              <Badge color={predictedColor(row.predicted_label)}>{row.predicted_label || "unknown"}</Badge>
              <Badge color={row.gpt_status === "done" ? "emerald" : row.gpt_status === "failed" ? "rose" : "amber"} size="xs">
                GPT {row.gpt_status || "pending"}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <MetricPill label="Customer" value={row.customer_count ?? 0} />
              <MetricPill label="Staff" value={row.staff_count ?? 0} />
              <MetricPill label="Banner" value={row.banner_count ?? 0} />
              <MetricPill label="Pedestrian" value={row.pedestrian_count ?? 0} />
            </div>
          </div>
        </div>

        {/* Reviewer label */}
        <div>
          <label className="block text-[10px] text-slate-400 mb-1 uppercase tracking-wide">Your Label (correction)</label>
          <select
            aria-label="Reviewer label correction"
            className="w-full border rounded-lg px-2.5 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-300"
            value={corrected}
            onChange={(e) => setCorrected(e.target.value)}
          >
            <option value="">Select label</option>
            {LABELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>

        <textarea
          className="w-full border rounded-lg px-2.5 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-300 resize-none"
          placeholder="Why is this correct / incorrect? (optional)"
          rows={2}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />

        {/* Actions */}
        <div className="flex items-center justify-between gap-2">
          <a
            href={row.drive_link || row.source_url || "#"}
            target="_blank" rel="noreferrer"
            className={`text-xs inline-flex items-center gap-1 ${row.drive_link || row.source_url ? "text-blue-600 hover:text-blue-700" : "text-slate-300 pointer-events-none"}`}
          >
            Source <ExternalLink size={11} />
          </a>
          <div className="flex gap-1">
            <button
              type="button" onClick={() => save("confirmed")} disabled={saving}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-50"
            >
              <Check size={11} /> Confirm
            </button>
            <button
              type="button" onClick={() => save("rejected")} disabled={saving}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-50"
            >
              <X size={11} /> Reject
            </button>
            <button
              type="button" onClick={remove} title="Delete review row"
              className="p-2 rounded-lg text-slate-400 hover:text-rose-600 border border-slate-200 hover:border-rose-300"
            >
              <Trash2 size={11} />
            </button>
          </div>
        </div>

        {row.gpt_error && <p className="text-[11px] text-rose-500 break-words">{row.gpt_error}</p>}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────
export default function FrameReview() {
  const { storeId } = useStore();
  const [statusFilter, setStatusFilter] = useState("pending");
  const [gptFilter, setGptFilter] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const [cachedAt, setCachedAt] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [page, setPage] = useState(0);

  function flash(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  }

  async function load(force = false) {
    if (!storeId) return;
    const key = cacheKey(storeId, statusFilter, dateFilter);

    // Use cache on navigation back (not on explicit refresh)
    if (!force) {
      const cached = readCache(key);
      if (cached) {
        setRows(cached.rows);
        setCachedAt(cached.ts);
        setPage(0);
        return;
      }
    }

    setLoading(true);
    setCachedAt(null);
    setPage(0);
    qaReviewQueue(storeId, statusFilter || undefined, dateFilter || undefined, 150)
      .then((r) => {
        setRows(r.data);
        writeCache(key, r.data);
        setCachedAt(Date.now());
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (storeId) void load();
  }, [storeId, statusFilter, dateFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSaved(updated: any) {
    flash("Review saved");
    setRows((prev) => prev.map((r) => r.image_id === updated.image_id ? updated : r));
    // Invalidate cache so next visit gets fresh data
    if (storeId) sessionStorage.removeItem(cacheKey(storeId, statusFilter, dateFilter));
  }

  function handleDeleted(imageId: string) {
    flash("Review removed");
    setRows((prev) => prev.filter((r) => r.image_id !== imageId));
    if (storeId) sessionStorage.removeItem(cacheKey(storeId, statusFilter, dateFilter));
  }

  const dateOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.capture_date).filter(Boolean))).sort().reverse(),
    [rows],
  );

  const filteredRows = useMemo(() => {
    if (!gptFilter) return rows;
    return rows.filter((r) => (r.gpt_status || "pending") === gptFilter);
  }, [rows, gptFilter]);

  const pending   = rows.filter((r) => (r.review_status || "pending") === "pending").length;
  const confirmed = rows.filter((r) => r.review_status === "confirmed").length;
  const rejected  = rows.filter((r) => r.review_status === "rejected").length;
  const gptFailed = rows.filter((r) => r.gpt_status === "failed").length;

  const totalPages = Math.ceil(filteredRows.length / PAGE_SIZE);
  const pageRows   = filteredRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Cache age label
  const cacheAgeLabel = cachedAt
    ? (() => {
        const secs = Math.floor((Date.now() - cachedAt) / 1000);
        if (secs < 60) return `${secs}s ago`;
        return `${Math.floor(secs / 60)}m ago`;
      })()
    : null;

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>
      )}

      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Title>Frame Review</Title>
          <Text>
            Review frame thumbnails. Step 1 = what YOLO found. Step 2 = what GPT classified.
            Confirm or reject to feed corrections into model retraining.
          </Text>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <select
            aria-label="Filter by review status"
            value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="">All Status</option>
            <option value="pending">Pending</option>
            <option value="confirmed">Confirmed</option>
            <option value="rejected">Rejected</option>
          </select>
          <select
            aria-label="Filter by date"
            value={dateFilter} onChange={(e) => setDateFilter(e.target.value)}
            className="h-9 px-3 rounded-lg border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="">All Dates</option>
            {dateOptions.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <select
            aria-label="Filter by GPT status"
            value={gptFilter} onChange={(e) => { setGptFilter(e.target.value); setPage(0); }}
            className="h-9 px-3 rounded-lg border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="">All GPT Status</option>
            <option value="failed">GPT Failed ⚠</option>
            <option value="done">GPT Done</option>
            <option value="pending">GPT Pending</option>
          </select>
          <button
            type="button" onClick={() => void load(true)}
            className="p-2 rounded border text-slate-500 hover:text-blue-600 hover:border-blue-400"
            title="Force refresh (bypass cache)"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Cache indicator */}
      {cacheAgeLabel && !loading && (
        <p className="text-[11px] text-slate-400">
          Showing cached results from {cacheAgeLabel}.{" "}
          <button type="button" onClick={() => void load(true)} className="underline hover:text-slate-600">Refresh now</button>
        </p>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="p-4">
          <Text className="text-xs uppercase tracking-wide text-slate-400">Pending</Text>
          <p className="text-2xl font-bold mt-1 text-amber-600">{pending}</p>
        </Card>
        <Card className="p-4">
          <Text className="text-xs uppercase tracking-wide text-slate-400">Confirmed</Text>
          <p className="text-2xl font-bold mt-1 text-emerald-600">{confirmed}</p>
        </Card>
        <Card className="p-4">
          <Text className="text-xs uppercase tracking-wide text-slate-400">Rejected</Text>
          <p className="text-2xl font-bold mt-1 text-rose-600">{rejected}</p>
        </Card>
        <button
          type="button"
          className="text-left p-4 rounded-lg border border-rose-200 bg-rose-50/50 hover:bg-rose-50 cursor-pointer transition-colors"
          onClick={() => { setGptFilter(gptFilter === "failed" ? "" : "failed"); setPage(0); }}
        >
          <Text className="text-xs uppercase tracking-wide text-rose-400">GPT Failed</Text>
          <p className="text-2xl font-bold mt-1 text-rose-600">{gptFailed}</p>
          <p className="text-[10px] text-rose-400 mt-0.5">{gptFilter === "failed" ? "▸ Filtering" : "Click to filter"}</p>
        </button>
        <Card className="p-4">
          <Text className="text-xs uppercase tracking-wide text-slate-400">Loaded</Text>
          <p className="text-2xl font-bold mt-1 text-slate-700">{rows.length}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">of last 150</p>
        </Card>
      </div>

      {/* How-to guide */}
      <Card className="p-4 bg-slate-50">
        <p className="font-semibold text-slate-700 mb-2 text-sm">How this feeds model retraining</p>
        <ol className="space-y-1 text-sm text-slate-600 list-decimal list-inside">
          <li><span className="font-medium text-blue-700">Step 1 (YOLO)</span> — shows raw person count and confidence. Low confidence = possible false positive.</li>
          <li><span className="font-medium text-purple-700">Step 2 (GPT)</span> — shows semantic classification: customer, staff, banner, pedestrian.</li>
          <li>Select your label correction and click <span className="font-semibold">Confirm</span> (GPT was right) or <span className="font-semibold">Reject</span> (GPT was wrong).</li>
          <li>After 200+ confirmations, go to <span className="font-semibold">Model Feedback → Generate Rule File</span> to create a retraining dataset.</li>
        </ol>
      </Card>

      {!storeId ? (
        <div className="text-center py-20 text-slate-400 text-sm">
          <p className="text-base font-medium text-slate-500 mb-2">Select a store to begin reviewing</p>
          <p>Use the store selector in the top navigation bar.</p>
        </div>
      ) : loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading frames…</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">
          No review rows found. Run the pipeline first, or change filters.
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between text-sm text-slate-500">
            <span>
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filteredRows.length)} of {filteredRows.length}
              {gptFilter ? " (filtered)" : ""}
              {" "}frames
            </span>
            <div className="flex items-center gap-2">
              <button type="button" title="Previous page" disabled={page === 0} onClick={() => setPage(p => p - 1)}
                className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100">
                <ChevronLeft size={16} />
              </button>
              <span>Page {page + 1} / {totalPages}</span>
              <button type="button" title="Next page" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
                className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100">
                <ChevronRight size={16} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
            {pageRows.map((r) => (
              <FeedbackCard
                key={`${r.store_id}:${r.image_id}`}
                row={r}
                onSaved={handleSaved}
                onDelete={handleDeleted}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2">
              <button type="button" title="Previous page" disabled={page === 0}
                onClick={() => { setPage(p => p - 1); window.scrollTo(0, 0); }}
                className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100">
                <ChevronLeft size={16} />
              </button>
              {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => (
                <button
                  type="button" key={i} title={`Page ${i + 1}`}
                  onClick={() => { setPage(i); window.scrollTo(0, 0); }}
                  className={`w-8 h-8 rounded text-sm ${page === i ? "bg-blue-600 text-white" : "border hover:bg-slate-50 text-slate-600"}`}
                >{i + 1}</button>
              ))}
              <button type="button" title="Next page" disabled={page >= totalPages - 1}
                onClick={() => { setPage(p => p + 1); window.scrollTo(0, 0); }}
                className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100">
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
