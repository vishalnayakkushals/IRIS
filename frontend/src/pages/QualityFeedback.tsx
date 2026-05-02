import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { reportsWalkins, qaFrameImageUrl } from "../api/client";
import { useStore } from "../context/StoreContext";
import { RefreshCw, ZoomIn } from "lucide-react";

type ReviewState = "pending" | "approved" | "rejected";

const PAGE_SIZE = 20;

// ── Hover image preview portal ─────────────────────────────────────────────
function HoverPreview({ src, rect }: { src: string; rect: DOMRect }) {
  const W = 360, H = 270, margin = 12;
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = rect.right + margin;
  let top  = rect.top + rect.height / 2 - H / 2;
  if (left + W > vw - margin) left = rect.left - W - margin;
  if (top < margin) top = margin;
  if (top + H > vh - margin) top = vh - H - margin;

  return createPortal(
    <div
      className="fixed z-[9999] rounded-xl overflow-hidden border-2 border-white pointer-events-none"
      style={{ left, top, width: W, height: H,
        boxShadow: "0 20px 60px rgba(0,0,0,0.4)",
        transition: "opacity 0.12s ease", opacity: 1 }}
    >
      <img src={src} alt="preview" className="w-full h-full object-cover" />
    </div>,
    document.body,
  );
}

// ── Thumbnail cell ─────────────────────────────────────────────────────────
function SessionThumb({ storeId, imageId, label }: { storeId: string; imageId: string; label: string }) {
  const [hoverRect, setHoverRect] = useState<DOMRect | null>(null);
  const [imgError, setImgError] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const src = qaFrameImageUrl(storeId, imageId);

  if (!imageId || imgError) {
    return <div className="w-16 h-12 rounded bg-slate-100 flex items-center justify-center text-[9px] text-slate-400">no img</div>;
  }

  return (
    <div
      ref={ref}
      className="relative w-16 h-12 rounded overflow-hidden bg-slate-100 cursor-zoom-in shrink-0 group"
      onMouseEnter={() => setHoverRect(ref.current?.getBoundingClientRect() ?? null)}
      onMouseLeave={() => setHoverRect(null)}
    >
      {hoverRect && <HoverPreview src={src} rect={hoverRect} />}
      <img
        src={src}
        alt={label}
        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
        loading="lazy"
        onError={() => setImgError(true)}
      />
      <div className="absolute inset-0 flex items-end justify-start p-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <span className="text-[8px] bg-black/60 text-white px-1 rounded">{label}</span>
      </div>
    </div>
  );
}

// ── Role badge ─────────────────────────────────────────────────────────────
function RoleBadge({ role }: { role: string }) {
  const r = (role || "").toLowerCase();
  const cls = r === "customer" ? "bg-sky-100 text-sky-700"
    : r === "staff" ? "bg-violet-100 text-violet-700"
    : "bg-slate-100 text-slate-500";
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold capitalize ${cls}`}>{role || "—"}</span>;
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function QualityFeedback() {
  const { storeId, storeName } = useStore();
  const [rows, setRows] = useState<any[]>([]);
  const [reviews, setReviews] = useState<Record<string, ReviewState>>({});
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [page, setPage] = useState(0);

  function load() {
    setLoading(true);
    setRows([]);
    setPage(0);
    const limit = storeId ? 300 : 200;
    reportsWalkins(storeId || undefined, undefined, limit)
      .then((r) => {
        const data: any[] = Array.isArray(r.data) ? r.data : [];
        // Only show sessions with a known role (GPT-analysed)
        setRows(data.filter((s) => (s.Role || s.role || "").trim()));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, [storeId]);

  function setReview(key: string, state: ReviewState) {
    setReviews((prev) => ({ ...prev, [key]: state }));
  }

  const getKey = (s: any) => s.walkin_id || s["Walk-in ID"] || s.id || Math.random().toString();
  const getRole = (s: any) => s.role || s.Role || "";
  const getDate = (s: any) => s.Date || s.date || s.business_date || "";
  const getStore = (s: any) => s.store_id || "";
  const getImageId = (s: any) => s.image_id || "";
  const getEntry = (s: any) => s["Entry Time"] || s.entry_time || "";
  const getExit  = (s: any) => s["Exit Time"]  || s.exit_time  || "";
  const getDwell = (s: any) => s["Time Spent (mins)"] || s.time_spent_mins || "";
  const getGender= (s: any) => s.Gender || s.gender || "";
  const getWalkinId = (s: any) => s["Walk-in ID"] || s.walkin_id || "";
  const getCamera = (s: any) => s.camera_id || "";
  const getFirstSeen = (s: any) => s.first_seen_time || "";
  const getLastSeen  = (s: any) => s.last_seen_time  || "";
  // Annotate rows with review state
  const annotated = useMemo(() => rows.map((s) => ({
    s,
    key: getKey(s),
    review: reviews[getKey(s)] ?? "pending" as ReviewState,
  })), [rows, reviews]);

  const filtered = filter === "all" ? annotated : annotated.filter((r) => r.review === filter);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageRows = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const counts = {
    pending:  annotated.filter((r) => r.review === "pending").length,
    approved: annotated.filter((r) => r.review === "approved").length,
    rejected: annotated.filter((r) => r.review === "rejected").length,
  };

  const subtitle = storeId ? (storeName || storeId) : "All Stores";

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Quality Assurance Review</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            GPT-analysed walk-in sessions — {subtitle}. Approve or reject before model retraining.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4 text-sm">
        {(["pending", "approved", "rejected"] as const).map((s) => (
          <button
            key={s}
            onClick={() => { setFilter(filter === s ? "all" : s); setPage(0); }}
            className={`border rounded-lg px-4 py-3 text-left transition-colors ${
              filter === s ? "border-blue-400 bg-blue-50" : "hover:bg-slate-50 border-slate-200"
            }`}
          >
            <p className="text-slate-400 text-xs capitalize mb-1">{s}</p>
            <p className="text-2xl font-bold text-slate-800">{loading ? "—" : counts[s]}</p>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center text-sm text-slate-400 py-12">Loading sessions…</div>
      ) : rows.length === 0 ? (
        <div className="text-center text-sm text-slate-400 py-12">
          No analysed sessions found{storeId ? ` for ${subtitle}` : ""}. Run a GPT pipeline cycle first.
        </div>
      ) : (
        <>
          {/* Row count + pagination controls */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-xs text-slate-400">
              {filtered.length > 0
                ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, filtered.length)} of ${filtered.length} sessions`
                : "No sessions match filter"}
              {filter !== "all" && (
                <button onClick={() => setFilter("all")} className="ml-2 underline hover:text-slate-600">
                  Clear filter
                </button>
              )}
            </p>
            {totalPages > 1 && (
              <div className="flex items-center gap-1 text-xs">
                <button
                  disabled={page === 0}
                  onClick={() => setPage(p => p - 1)}
                  className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >← Prev</button>
                <span className="px-2 text-slate-500">Page {page + 1} / {totalPages}</span>
                <button
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage(p => p + 1)}
                  className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >Next →</button>
              </div>
            )}
          </div>

          {/* Table */}
          <div className="overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-500 text-left border-b border-slate-200">
                  <th className="px-3 py-2.5 font-semibold">Source Image</th>
                  <th className="px-3 py-2.5 font-semibold">Date</th>
                  <th className="px-3 py-2.5 font-semibold">Store</th>
                  <th className="px-3 py-2.5 font-semibold">Role</th>
                  <th className="px-3 py-2.5 font-semibold">Entry → Exit</th>
                  <th className="px-3 py-2.5 font-semibold">Dwell</th>
                  <th className="px-3 py-2.5 font-semibold">Gender</th>
                  <th className="px-3 py-2.5 font-semibold">Camera</th>
                  <th className="px-3 py-2.5 font-semibold">Walk-in ID</th>
                  <th className="px-3 py-2.5 font-semibold text-center">Action</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.length === 0 && (
                  <tr>
                    <td colSpan={10} className="text-center py-10 text-slate-400">
                      No sessions match the current filter.
                    </td>
                  </tr>
                )}
                {pageRows.map(({ s, key, review }) => {
                  const storeIdVal = getStore(s);
                  const imageId = getImageId(s);
                  const entry = getEntry(s);
                  const exit  = getExit(s);
                  const firstSeen = getFirstSeen(s);
                  const lastSeen  = getLastSeen(s);

                  return (
                    <tr
                      key={key}
                      className={`border-t border-slate-100 transition-colors ${
                        review === "approved" ? "bg-emerald-50/50"
                        : review === "rejected" ? "bg-rose-50/50"
                        : "hover:bg-slate-50/50"
                      }`}
                    >
                      {/* Source image thumbnail + first/last seen */}
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1.5">
                          {imageId ? (
                            <>
                              <div className="flex flex-col items-center gap-1">
                                <SessionThumb storeId={storeIdVal} imageId={imageId} label={firstSeen || entry || "entry"} />
                                {firstSeen && <span className="text-[8px] text-slate-400 truncate w-16 text-center">{firstSeen.slice(0, 8)}</span>}
                              </div>
                              {lastSeen && lastSeen !== firstSeen && (
                                <div className="flex flex-col items-center gap-1">
                                  <SessionThumb storeId={storeIdVal} imageId={imageId} label={lastSeen || exit || "exit"} />
                                  <span className="text-[8px] text-slate-400 truncate w-16 text-center">{lastSeen.slice(0, 8)}</span>
                                </div>
                              )}
                            </>
                          ) : (
                            <div className="flex items-center gap-1 text-slate-300">
                              <ZoomIn size={12} />
                              <span className="text-[9px]">no image</span>
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{getDate(s)}</td>
                      <td className="px-3 py-2 font-mono text-[10px] text-slate-500 whitespace-nowrap">{storeIdVal}</td>
                      <td className="px-3 py-2"><RoleBadge role={getRole(s)} /></td>
                      <td className="px-3 py-2 whitespace-nowrap text-slate-600">
                        {entry || "—"} → {exit || "—"}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{getDwell(s) ? `${getDwell(s)}m` : "—"}</td>
                      <td className="px-3 py-2 capitalize">{getGender(s) || "—"}</td>
                      <td className="px-3 py-2 text-slate-500">{getCamera(s) || "—"}</td>
                      <td className="px-3 py-2 font-mono text-[9px] text-slate-400 max-w-[80px] truncate" title={getWalkinId(s)}>
                        {getWalkinId(s)?.slice(0, 10) || "—"}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex gap-1 justify-center">
                          <button
                            onClick={() => setReview(key, review === "approved" ? "pending" : "approved")}
                            className={`px-2.5 py-1 rounded text-[10px] font-medium transition-colors ${
                              review === "approved"
                                ? "bg-emerald-600 text-white"
                                : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                            }`}
                          >✓</button>
                          <button
                            onClick={() => setReview(key, review === "rejected" ? "pending" : "rejected")}
                            className={`px-2.5 py-1 rounded text-[10px] font-medium transition-colors ${
                              review === "rejected"
                                ? "bg-rose-600 text-white"
                                : "bg-rose-50 text-rose-700 hover:bg-rose-100"
                            }`}
                          >✗</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Bottom pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-1 text-xs pt-1">
              <button disabled={page === 0} onClick={() => { setPage(p => p - 1); window.scrollTo(0, 0); }}
                className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50">← Prev</button>
              {Array.from({ length: Math.min(totalPages, 8) }, (_, i) => (
                <button key={i} onClick={() => { setPage(i); window.scrollTo(0, 0); }}
                  className={`w-8 h-8 rounded text-xs ${page === i ? "bg-blue-600 text-white" : "border border-slate-200 hover:bg-slate-50 text-slate-600"}`}
                >{i + 1}</button>
              ))}
              <button disabled={page >= totalPages - 1} onClick={() => { setPage(p => p + 1); window.scrollTo(0, 0); }}
                className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50">Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
