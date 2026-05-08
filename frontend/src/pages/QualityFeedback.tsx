import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  reportsWalkinsQA,
  qaCreateFeedback,
  qaUpdateFeedback,
  qaFrameImageUrl,
} from "../api/client";
import { useStore } from "../context/StoreContext";
import { RefreshCw, ZoomIn, Check, X, Loader2 } from "lucide-react";

type ReviewState = "pending" | "approved" | "rejected";

interface FeedbackEntry {
  status: ReviewState;
  feedbackId?: number;
  correctedLabel?: string;
}

const PAGE_SIZE = 25;
const ROLE_OPTIONS = ["customer", "staff", "uncertain", "no_human"];

// ── Hover image preview portal ─────────────────────────────────────────────
function HoverPreview({ src, rect }: { src: string; rect: DOMRect }) {
  const W = 380, H = 285, margin = 12;
  const vw = window.innerWidth, vh = window.innerHeight;
  let left = rect.right + margin;
  let top  = rect.top + rect.height / 2 - H / 2;
  if (left + W > vw - margin) left = rect.left - W - margin;
  if (top < margin) top = margin;
  if (top + H > vh - margin) top = vh - H - margin;
  return createPortal(
    <div
      className="fixed z-[9999] rounded-xl overflow-hidden border-2 border-white pointer-events-none"
      style={{ left, top, width: W, height: H, boxShadow: "0 24px 64px rgba(0,0,0,0.45)", opacity: 1 }}
    >
      <img src={src} alt="preview" className="w-full h-full object-cover" />
    </div>,
    document.body,
  );
}

// ── Single thumbnail ───────────────────────────────────────────────────────
function SessionThumb({ storeId, imageId, label }: { storeId: string; imageId: string; label?: string }) {
  const [hoverRect, setHoverRect] = useState<DOMRect | null>(null);
  const [imgError, setImgError] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  if (!imageId || imgError) {
    return (
      <div className="w-14 h-10 rounded bg-slate-100 flex items-center justify-center shrink-0">
        <ZoomIn size={11} className="text-slate-300" />
      </div>
    );
  }
  const src = qaFrameImageUrl(storeId, imageId);
  return (
    <div
      ref={ref}
      className="relative w-14 h-10 rounded overflow-hidden bg-slate-100 cursor-zoom-in shrink-0 group border border-slate-200"
      onMouseEnter={() => setHoverRect(ref.current?.getBoundingClientRect() ?? null)}
      onMouseLeave={() => setHoverRect(null)}
    >
      {hoverRect && <HoverPreview src={src} rect={hoverRect} />}
      <img
        src={src} alt={label || "frame"}
        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
        loading="lazy" onError={() => setImgError(true)}
      />
      {label && (
        <div className="absolute inset-0 flex items-end justify-start p-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="text-[7px] bg-black/60 text-white px-1 rounded leading-tight">{label}</span>
        </div>
      )}
    </div>
  );
}

// ── Role badge ─────────────────────────────────────────────────────────────
function RoleBadge({ role }: { role: string }) {
  const r = (role || "").toLowerCase();
  const cls = r === "customer" ? "bg-sky-100 text-sky-700 border-sky-200"
    : r === "staff" ? "bg-violet-100 text-violet-700 border-violet-200"
    : "bg-slate-100 text-slate-500 border-slate-200";
  return <span className={`inline-block px-2 py-0.5 rounded border text-[10px] font-semibold capitalize ${cls}`}>{role || "—"}</span>;
}

// ── Analytics badge ────────────────────────────────────────────────────────
function AnalyticsBadge({ value }: { value: string }) {
  const v = (value || "").toLowerCase();
  const cls = v === "yes" ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : v === "no" ? "bg-rose-50 text-rose-700 border-rose-200"
    : "bg-slate-50 text-slate-400 border-slate-200";
  return <span className={`inline-block px-2 py-0.5 rounded border text-[10px] font-semibold ${cls}`}>{value || "—"}</span>;
}

// ── Reject correction picker ───────────────────────────────────────────────
function RejectPicker({ onPick, onCancel }: { onPick: (label: string) => void; onCancel: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 flex flex-col items-center gap-4 min-w-[280px]">
        <p className="text-sm font-semibold text-slate-800">What is the correct label?</p>
        <div className="flex flex-wrap gap-2 justify-center">
          {ROLE_OPTIONS.map((opt) => (
            <button
              type="button"
              key={opt}
              onClick={() => onPick(opt)}
              className="px-4 py-2 rounded-lg text-sm font-semibold border border-slate-300 bg-slate-50 hover:border-blue-500 hover:bg-blue-50 hover:text-blue-700 transition-colors capitalize"
            >
              {opt.replace("_", " ")}
            </button>
          ))}
        </div>
        <button type="button" onClick={onCancel} className="text-xs text-slate-400 hover:text-slate-600 transition-colors">Cancel</button>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function QualityFeedback() {
  const { storeId, storeName } = useStore();
  const [rows, setRows] = useState<any[]>([]);
  const [feedbackState, setFeedbackState] = useState<Record<string, FeedbackEntry>>({});
  const [saving, setSaving] = useState<Set<string>>(new Set());
  const [rejectPicker, setRejectPicker] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [page, setPage] = useState(0);
  const [toast, setToast] = useState("");

  function flash(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 2500);
  }

  const CACHE_TTL_MS = 5 * 60 * 1000;

  function getCacheKey() { return `qa_sessions_${storeId || "all"}`; }

  function readCache(): any[] | null {
    try {
      const raw = sessionStorage.getItem(getCacheKey());
      if (!raw) return null;
      const { data, ts } = JSON.parse(raw);
      if (Date.now() - ts > CACHE_TTL_MS) { sessionStorage.removeItem(getCacheKey()); return null; }
      return data;
    } catch { return null; }
  }

  function writeCache(data: any[]) {
    try { sessionStorage.setItem(getCacheKey(), JSON.stringify({ data, ts: Date.now() })); } catch {}
  }

  function load(force = false) {
    const cached = !force && readCache();
    if (cached) { setRows(cached); setFeedbackState({}); setPage(0); return; }
    setLoading(true);
    setError("");
    setPage(0);
    reportsWalkinsQA(storeId || undefined, 100)
      .then((r) => {
        const data: any[] = Array.isArray(r.data) ? r.data : [];
        setRows(data);
        setFeedbackState({});
        writeCache(data);
      })
      .catch(() => setError("Failed to load sessions. Check the server is running."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, [storeId]); // eslint-disable-line react-hooks/exhaustive-deps

  const getKey     = (s: any) => String(s.walkin_id || s.id || Math.random());
  const getRole    = (s: any) => s.role || "";
  const getDate    = (s: any) => s.date || s.business_date || "";
  const getStore   = (s: any) => s.store_id || "";
  const getImageId = (s: any) => s.image_id || "";
  const getLastImageId = (s: any) => s.last_image_id || s.image_id || "";
  const getEntry   = (s: any) => s.entry_time || "";
  const getExit    = (s: any) => s.exit_time || "";
  const getDwell   = (s: any) => s.time_spent_mins || "";
  const getGender  = (s: any) => s.gender || "";
  const getWalkinId= (s: any) => s.walkin_id || "";
  const getAnalytics=(s: any) => s.included_in_analytics || "";
  const getFirst   = (s: any) => s.first_seen_time || "";
  const getLast    = (s: any) => s.last_seen_time || "";

  async function saveApprove(key: string, s: any) {
    setSaving((prev) => new Set(prev).add(key));
    const role = getRole(s);
    try {
      const existing = feedbackState[key];
      if (existing?.feedbackId) {
        await qaUpdateFeedback(existing.feedbackId, { review_status: "confirmed", corrected_label: role });
        setFeedbackState((prev) => ({ ...prev, [key]: { ...existing, status: "approved" } }));
      } else {
        const res = await qaCreateFeedback({
          store_id: getStore(s),
          capture_date: getDate(s),
          filename: s.source_image_name || getImageId(s),
          camera_id: s.camera_id || "",
          track_id: getWalkinId(s),
          predicted_label: role,
          corrected_label: role,
          confidence: 0.9,
          needs_review: false,
          review_status: "confirmed",
        });
        setFeedbackState((prev) => ({
          ...prev,
          [key]: { status: "approved", feedbackId: res.data.id, correctedLabel: role },
        }));
      }
      flash("Approved ✓");
    } catch {
      flash("Save failed — check server");
    } finally {
      setSaving((prev) => { const s = new Set(prev); s.delete(key); return s; });
    }
  }

  async function saveReject(key: string, s: any, correctedLabel: string) {
    setRejectPicker(null);
    setSaving((prev) => new Set(prev).add(key));
    const role = getRole(s);
    try {
      const existing = feedbackState[key];
      if (existing?.feedbackId) {
        await qaUpdateFeedback(existing.feedbackId, { review_status: "rejected", corrected_label: correctedLabel });
        setFeedbackState((prev) => ({ ...prev, [key]: { ...existing, status: "rejected", correctedLabel } }));
      } else {
        const res = await qaCreateFeedback({
          store_id: getStore(s),
          capture_date: getDate(s),
          filename: s.source_image_name || getImageId(s),
          camera_id: s.camera_id || "",
          track_id: getWalkinId(s),
          predicted_label: role,
          corrected_label: correctedLabel,
          confidence: 0.9,
          needs_review: true,
          review_status: "rejected",
        });
        setFeedbackState((prev) => ({
          ...prev,
          [key]: { status: "rejected", feedbackId: res.data.id, correctedLabel },
        }));
      }
      flash("Rejected — label saved ✓");
    } catch {
      flash("Save failed — check server");
    } finally {
      setSaving((prev) => { const s = new Set(prev); s.delete(key); return s; });
    }
  }

  const annotated = useMemo(() => rows.map((s) => {
    const key = getKey(s);
    const fb = feedbackState[key];
    return { s, key, review: fb?.status ?? ("pending" as ReviewState), correctedLabel: fb?.correctedLabel };
  }), [rows, feedbackState]); // eslint-disable-line react-hooks/exhaustive-deps

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
      {toast && (
        <div className="fixed top-20 right-6 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">QA Overview — Walk-in Sessions</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Review GPT-analysed walk-in sessions. Approve correct detections or reject and label the actual role to feed model retraining.
          </p>
        </div>
        <button
          onClick={() => load(true)} disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Summary cards — clickable filter */}
      <div className="grid grid-cols-3 gap-4 text-sm">
        {(["pending", "approved", "rejected"] as const).map((s) => (
          <button
            key={s}
            onClick={() => { setFilter(filter === s ? "all" : s); setPage(0); }}
            className={`border rounded-xl px-4 py-3 text-left transition-all ${
              filter === s ? "border-blue-400 bg-blue-50 shadow-sm" : "hover:bg-slate-50 border-slate-200"
            }`}
          >
            <p className="text-slate-400 text-xs capitalize mb-1">{s}</p>
            <p className="text-2xl font-bold text-slate-800">{loading ? "—" : counts[s]}</p>
          </button>
        ))}
      </div>

      {/* Retraining progress hint */}
      {counts.approved + counts.rejected > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 text-sm text-blue-800">
          <span className="font-semibold">{counts.approved + counts.rejected} sessions reviewed</span>
          {counts.approved + counts.rejected < 200 && (
            <span className="text-blue-600">
              {" "}— review at least <span className="font-semibold">200</span> to generate a quality retraining rule file on the Model Feedback page.
            </span>
          )}
          {counts.approved + counts.rejected >= 200 && (
            <span className="text-emerald-700 font-semibold"> ✓ Enough data to retrain. Go to Model Feedback → Generate Rule File.</span>
          )}
        </div>
      )}

      {loading && <div className="text-center text-sm text-slate-400 py-14">Loading sessions…</div>}
      {!loading && error && <div className="text-center text-sm text-rose-500 py-10">{error}</div>}
      {!loading && !error && rows.length === 0 && (
        <div className="text-center text-sm text-slate-400 py-14">
          No GPT-analysed sessions found{storeId ? ` for ${subtitle}` : ""}. Run a pipeline cycle first.
        </div>
      )}

      {!loading && !error && rows.length > 0 && (
        <>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-xs text-slate-400">
              {filtered.length === 0
                ? "No sessions match filter"
                : `Showing ${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, filtered.length)} of ${filtered.length} sessions`}
              {filter !== "all" && (
                <button onClick={() => { setFilter("all"); setPage(0); }} className="ml-2 underline hover:text-slate-600">Clear filter</button>
              )}
            </p>
            {totalPages > 1 && (
              <div className="flex items-center gap-1 text-xs">
                <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
                  className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50">← Prev</button>
                <span className="px-2 text-slate-500">Page {page + 1} / {totalPages}</span>
                <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
                  className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50">Next →</button>
              </div>
            )}
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-500 text-left border-b border-slate-200">
                  <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Date</th>
                  <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Store</th>
                  <th className="px-3 py-2.5 font-semibold">Walk-in ID</th>
                  <th className="px-3 py-2.5 font-semibold whitespace-nowrap">GPT Label</th>
                  <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Frames</th>
                  <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Entry → Exit</th>
                  <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Dwell</th>
                  <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Gender</th>
                  <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Analytics</th>
                  <th className="px-3 py-2.5 font-semibold text-center whitespace-nowrap">Review</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.length === 0 && (
                  <tr><td colSpan={10} className="text-center py-12 text-slate-400">No sessions match the current filter.</td></tr>
                )}
                {pageRows.map(({ s, key, review, correctedLabel }) => {
                  const sid        = getStore(s);
                  const imgId      = getImageId(s);
                  const lastImgId  = getLastImageId(s);
                  const entry      = getEntry(s);
                  const exit       = getExit(s);
                  const first      = getFirst(s);
                  const last       = getLast(s);
                  const isSaving   = saving.has(key);
                  const showPicker = rejectPicker === key;

                  return (
                    <tr
                      key={key}
                      className={`border-t border-slate-100 transition-colors ${
                        review === "approved" ? "bg-emerald-50/40"
                        : review === "rejected" ? "bg-rose-50/40"
                        : "hover:bg-slate-50/60"
                      }`}
                    >
                      <td className="px-3 py-2 whitespace-nowrap text-slate-600">{getDate(s) || "—"}</td>
                      <td className="px-3 py-2 font-mono text-[10px] text-slate-500 whitespace-nowrap">{sid || "—"}</td>
                      <td className="px-3 py-2">
                        <div className="font-mono text-[10px] text-slate-600 leading-tight" style={{ wordBreak: "break-all", minWidth: 90, maxWidth: 140 }}>
                          {getWalkinId(s) || "—"}
                        </div>
                      </td>

                      {/* GPT Label + corrected */}
                      <td className="px-3 py-2">
                        <div className="flex flex-col gap-0.5">
                          <RoleBadge role={getRole(s)} />
                          {review === "rejected" && correctedLabel && correctedLabel !== getRole(s) && (
                            <span className="text-[9px] text-rose-600">→ {correctedLabel}</span>
                          )}
                        </div>
                      </td>

                      {/* Frames: entry thumbnail + exit thumbnail */}
                      <td className="px-3 py-2">
                        {imgId ? (
                          <div className="flex items-center gap-1">
                            <div className="flex flex-col items-center gap-0.5">
                              <SessionThumb storeId={sid} imageId={imgId} label="entry" />
                              {(first || entry) && (
                                <span className="text-[7px] text-slate-400 text-center leading-tight max-w-[56px] truncate">
                                  {(first || entry).slice(0, 8)}
                                </span>
                              )}
                            </div>
                            {lastImgId && lastImgId !== imgId && (
                              <div className="flex flex-col items-center gap-0.5">
                                <SessionThumb storeId={sid} imageId={lastImgId} label="exit" />
                                {(last || exit) && (
                                  <span className="text-[7px] text-slate-400 text-center leading-tight max-w-[56px] truncate">
                                    {(last || exit).slice(0, 8)}
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        ) : (
                          <span className="text-[9px] text-slate-300">no image</span>
                        )}
                      </td>

                      <td className="px-3 py-2 whitespace-nowrap text-slate-600">{entry || "—"} {exit ? `→ ${exit}` : ""}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{getDwell(s) ? `${getDwell(s)}m` : "—"}</td>
                      <td className="px-3 py-2 capitalize text-slate-600">{getGender(s) || "—"}</td>
                      <td className="px-3 py-2"><AnalyticsBadge value={getAnalytics(s)} /></td>

                      {/* Actions */}
                      <td className="px-3 py-2">
                        <div className="relative flex gap-1 justify-center">
                          {showPicker && (
                            <RejectPicker
                              onPick={(label) => saveReject(key, s, label)}
                              onCancel={() => setRejectPicker(null)}
                            />
                          )}
                          {isSaving ? (
                            <Loader2 size={16} className="animate-spin text-slate-400" />
                          ) : review === "approved" ? (
                            <span className="text-[10px] text-emerald-700 font-semibold px-1">✓ Approved</span>
                          ) : review === "rejected" ? (
                            <span className="text-[10px] text-rose-600 font-semibold px-1">✗ Rejected</span>
                          ) : (
                            <>
                              <button
                                onClick={() => saveApprove(key, s)}
                                className="w-7 h-7 rounded flex items-center justify-center bg-emerald-50 text-emerald-600 hover:bg-emerald-100 border border-emerald-200 transition-colors"
                                title="Approve — GPT label is correct"
                              ><Check size={12} /></button>
                              <button
                                onClick={() => setRejectPicker(key)}
                                className="w-7 h-7 rounded flex items-center justify-center bg-rose-50 text-rose-600 hover:bg-rose-100 border border-rose-200 transition-colors"
                                title="Reject — pick correct label"
                              ><X size={12} /></button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-1 text-xs pt-1 pb-4">
              <button disabled={page === 0} onClick={() => { setPage(p => p - 1); window.scrollTo(0, 0); }}
                className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50">← Prev</button>
              {Array.from({ length: Math.min(totalPages, 9) }, (_, i) => (
                <button key={i} onClick={() => { setPage(i); window.scrollTo(0, 0); }}
                  className={`w-8 h-8 rounded text-xs font-medium ${page === i ? "bg-blue-600 text-white shadow-sm" : "border border-slate-200 hover:bg-slate-50 text-slate-600"}`}
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
