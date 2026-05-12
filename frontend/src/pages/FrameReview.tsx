import { useEffect, useRef, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { qaReviewQueue, QAFrameRow, ReviewDateOption } from "../api/client";
import { useStore } from "../context/StoreContext";
import { FeedbackCard, PAGE_SIZE, cacheKey, readCache, writeCache } from "../features/frame-review/components";

function dateBounds(options: ReviewDateOption[]) {
  const values = options.map((option) => option.value).filter(Boolean).sort();
  return {
    min: values[0] ?? undefined,
    max: values[values.length - 1] ?? undefined,
  };
}

export default function FrameReview() {
  const { storeId } = useStore();
  const [statusFilter, setStatusFilter] = useState("");
  const [gptFilter, setGptFilter] = useState("");
  const [rows, setRows] = useState<QAFrameRow[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [dateOptions, setDateOptions] = useState<ReviewDateOption[]>([]);
  const [stats, setStats] = useState({ pending: 0, confirmed: 0, rejected: 0, gpt_failed: 0 });
  const [cachedAt, setCachedAt] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [page, setPage] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  function flash(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  }

  function load(force = false) {
    if (!storeId) return;
    const key = cacheKey(storeId, `${dateFilter}|${statusFilter}|${gptFilter}|${page}`);
    if (!force) {
      const cached = readCache(key);
      if (cached) {
        setRows(cached.rows);
        setTotalRows(cached.total ?? cached.rows.length);
        setDateOptions((cached.dates as ReviewDateOption[]) ?? []);
        setStats((cached.stats as typeof stats) ?? { pending: 0, confirmed: 0, rejected: 0, gpt_failed: 0 });
        setCachedAt(cached.ts);
        return;
      }
    }
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;
    setLoading(true);
    setCachedAt(null);
    qaReviewQueue(storeId, {
      reviewStatus: statusFilter || undefined,
      businessDate: dateFilter || undefined,
      gptStatus: gptFilter || undefined,
      offset: page * PAGE_SIZE,
      limit: PAGE_SIZE,
    }, { signal })
      .then((response) => {
        setRows(response.data.rows ?? []);
        setTotalRows(response.data.total ?? 0);
        setDateOptions(response.data.dates ?? []);
        setStats(response.data.stats ?? { pending: 0, confirmed: 0, rejected: 0, gpt_failed: 0 });
        writeCache(key, {
          rows: response.data.rows ?? [],
          total: response.data.total ?? 0,
          dates: response.data.dates ?? [],
          stats: response.data.stats ?? { pending: 0, confirmed: 0, rejected: 0, gpt_failed: 0 },
        });
        setCachedAt(Date.now());
      })
      .catch((error) => {
        if (error?.code !== "ERR_CANCELED") setRows([]);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (storeId) load();
    return () => {
      abortRef.current?.abort();
    };
  }, [storeId, dateFilter, statusFilter, gptFilter, page]);

  function handleSaved(updated: QAFrameRow) {
    flash("Review saved ✓");
    setRows((prev) => prev.map((row) => (row.image_id === updated.image_id ? updated : row)));
    if (storeId) {
      sessionStorage.removeItem(cacheKey(storeId, `${dateFilter}|${statusFilter}|${gptFilter}|${page}`));
      void load(true);
    }
  }

  function handleDeleted(imageId: string) {
    flash("Review removed");
    setRows((prev) => prev.filter((row) => row.image_id !== imageId));
    if (storeId) {
      sessionStorage.removeItem(cacheKey(storeId, `${dateFilter}|${statusFilter}|${gptFilter}|${page}`));
      void load(true);
    }
  }

  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
  const pageRows = rows;
  const availableDates = dateBounds(dateOptions);
  const cacheAgeLabel = cachedAt ? (() => {
    const secs = Math.floor((Date.now() - cachedAt) / 1000);
    return secs < 60 ? `${secs}s ago` : `${Math.floor(secs / 60)}m ago`;
  })() : null;

  return (
    <div className="space-y-6">
      {toast ? <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div> : null}

      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Title>Frame Review</Title>
          <Text>Review frame thumbnails. Step 1 = what YOLO found. Step 2 = what GPT classified. Confirm or reject to feed corrections into model retraining.</Text>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <select aria-label="Filter by review status" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }} className="h-9 px-3 rounded-lg border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
            <option value="">All Status</option><option value="pending">Pending</option><option value="confirmed">Confirmed</option><option value="rejected">Rejected</option>
          </select>
          <input
            aria-label="Filter by date"
            type="date"
            value={dateFilter}
            min={availableDates.min}
            max={availableDates.max}
            onChange={(e) => { setDateFilter(e.target.value); setPage(0); }}
            className="h-9 px-3 rounded-lg border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <button
            type="button"
            onClick={() => { setDateFilter(""); setPage(0); }}
            className="h-9 px-3 rounded-lg border border-slate-300 bg-white text-slate-600 text-sm hover:bg-slate-50"
          >
            All dates
          </button>
          <select aria-label="Filter by GPT status" value={gptFilter} onChange={(e) => { setGptFilter(e.target.value); setPage(0); }} className="h-9 px-3 rounded-lg border border-slate-300 bg-white text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
            <option value="">All GPT Status</option><option value="failed">GPT Failed ⚠</option><option value="done">GPT Done</option><option value="pending">GPT Pending</option>
          </select>
          <button type="button" onClick={() => void load(true)} className="p-2 rounded border text-slate-500 hover:text-blue-600 hover:border-blue-400" title="Force refresh (bypass cache)"><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        {cacheAgeLabel && !loading ? <p className="text-[11px] text-slate-400">Showing cached results from {cacheAgeLabel}. <button type="button" onClick={() => void load(true)} className="underline hover:text-slate-600">Refresh now</button></p> : <span />}
        <p className="text-[11px] text-slate-400">{dateOptions.length.toLocaleString()} scanned dates available</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Pending</Text><p className="text-2xl font-bold mt-1 text-amber-600">{stats.pending}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Confirmed</Text><p className="text-2xl font-bold mt-1 text-emerald-600">{stats.confirmed}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Rejected</Text><p className="text-2xl font-bold mt-1 text-rose-600">{stats.rejected}</p></Card>
        <button type="button" className="text-left p-4 rounded-lg border border-rose-200 bg-rose-50/50 hover:bg-rose-50 cursor-pointer transition-colors" onClick={() => { setGptFilter(gptFilter === "failed" ? "" : "failed"); setPage(0); }}>
          <Text className="text-xs uppercase tracking-wide text-rose-400">GPT Failed</Text><p className="text-2xl font-bold mt-1 text-rose-600">{stats.gpt_failed}</p><p className="text-[10px] text-rose-400 mt-0.5">{gptFilter === "failed" ? "▸ Filtering" : "Click to filter"}</p>
        </button>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Loaded</Text><p className="text-2xl font-bold mt-1 text-slate-700">{rows.length}</p><p className="text-[10px] text-slate-400 mt-0.5">of {totalRows}</p></Card>
      </div>

      <Card className="p-4 bg-slate-50">
        <p className="font-semibold text-slate-700 mb-2 text-sm">How this feeds model retraining</p>
        <ol className="space-y-1 text-sm text-slate-600 list-decimal list-inside">
          <li><span className="font-medium text-blue-700">Step 1 (YOLO)</span> — shows raw person count and confidence. Low confidence = possible false positive.</li>
          <li><span className="font-medium text-purple-700">Step 2 (GPT)</span> — shows semantic classification: customer, staff, banner, pedestrian.</li>
          <li>Select your label correction and click <span className="font-semibold">Confirm</span> or <span className="font-semibold">Reject</span>.</li>
          <li>After 200+ confirmations, go to <span className="font-semibold">Model Feedback → Generate Rule File</span> to create a retraining dataset.</li>
        </ol>
      </Card>

      {!storeId ? (
        <div className="text-center py-20 text-slate-400 text-sm"><p className="text-base font-medium text-slate-500 mb-2">Select a store to begin reviewing</p><p>Use the store selector in the top navigation bar.</p></div>
      ) : loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading frames…</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">No review rows found. Run the pipeline first, or change filters.</div>
      ) : (
        <>
          <div className="flex items-center justify-between text-sm text-slate-500">
            <span>Showing {page * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE + pageRows.length, totalRows)} of {totalRows}{gptFilter ? " (filtered)" : ""} frames</span>
            <div className="flex items-center gap-2">
              <button type="button" title="Previous page" disabled={page === 0} onClick={() => setPage((current) => current - 1)} className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100"><ChevronLeft size={16} /></button>
              <span>Page {page + 1} / {totalPages}</span>
              <button type="button" title="Next page" disabled={page >= totalPages - 1} onClick={() => setPage((current) => current + 1)} className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100"><ChevronRight size={16} /></button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
            {pageRows.map((row) => <FeedbackCard key={`${row.store_id}:${row.image_id}`} row={row} onSaved={handleSaved} onDelete={handleDeleted} onFlash={flash} />)}
          </div>
          {totalPages > 1 ? (
            <div className="flex items-center justify-center gap-2 pt-2">
              <button type="button" title="Previous page" disabled={page === 0} onClick={() => { setPage((current) => current - 1); window.scrollTo(0, 0); }} className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100"><ChevronLeft size={16} /></button>
              {Array.from({ length: Math.min(totalPages, 10) }, (_, index) => (
                <button key={index} type="button" title={`Page ${index + 1}`} onClick={() => { setPage(index); window.scrollTo(0, 0); }} className={`w-8 h-8 rounded text-sm ${page === index ? "bg-blue-600 text-white" : "border hover:bg-slate-50 text-slate-600"}`}>{index + 1}</button>
              ))}
              <button type="button" title="Next page" disabled={page >= totalPages - 1} onClick={() => { setPage((current) => current + 1); window.scrollTo(0, 0); }} className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100"><ChevronRight size={16} /></button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
