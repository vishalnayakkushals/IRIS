import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Badge } from "@tremor/react";
import { Check, Cpu, ExternalLink, Eye, ScanSearch, Trash2, X, Zap } from "lucide-react";
import { qaAnnotatedFrameImageUrl, qaCreateFeedback, qaDeleteFeedback, qaFrameImageUrl, qaUpdateFeedback } from "../../api/client";

export const LABELS = ["customer", "staff", "banner", "pedestrian", "unknown", "no_human"];
export const PAGE_SIZE = 24;
const CACHE_TTL_MS = 5 * 60 * 1000;

export function cacheKey(storeId: string, date: string) {
  return `fr-v2:${storeId}:${date}`;
}

export function readCache(key: string): { rows: any[]; ts: number } | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { rows: any[]; ts: number };
    if (Date.now() - parsed.ts > CACHE_TTL_MS) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeCache(key: string, rows: any[]) {
  try {
    sessionStorage.setItem(key, JSON.stringify({ rows, ts: Date.now() }));
  } catch {
    // cache quota exceeded — runtime state still works
  }
}

function HoverPreview({ src, rect }: { src: string; rect: DOMRect }) {
  const width = 320;
  const height = 240;
  const margin = 12;
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  let left = rect.right + margin;
  let top = rect.top + rect.height / 2 - height / 2;
  if (left + width > viewportWidth - margin) left = rect.left - width - margin;
  if (top < margin) top = margin;
  if (top + height > viewportHeight - margin) top = viewportHeight - height - margin;
  return createPortal(
    <div className="fixed z-[9999] rounded-xl overflow-hidden shadow-2xl border-2 border-white pointer-events-none" style={{ left, top, width, height, boxShadow: "0 20px 60px rgba(0,0,0,0.35)" }}>
      <img src={src} alt="preview" className="w-full h-full object-cover" />
    </div>,
    document.body,
  );
}

function statusColor(status: string) {
  if (status === "confirmed") return "emerald";
  if (status === "rejected") return "rose";
  return "amber";
}

function predictedColor(label: string) {
  const normalized = (label || "").toLowerCase();
  if (normalized === "customer") return "emerald";
  if (normalized === "staff") return "blue";
  if (normalized === "banner") return "orange";
  if (normalized === "pedestrian") return "violet";
  return "slate";
}

function StepHeader({ icon, step, label, color }: { icon: React.ReactNode; step: string; label: string; color: string }) {
  return <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-semibold ${color}`}>{icon}<span className="uppercase tracking-wide opacity-70">{step}</span><span>{label}</span></div>;
}

function MetricPill({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-md bg-slate-50 px-2 py-1 border border-slate-200 flex flex-col"><p className="text-[9px] uppercase tracking-wide text-slate-400 leading-tight">{label}</p><p className="text-sm font-semibold text-slate-700">{value}</p></div>;
}

export function FeedbackCard({ row, onSaved, onDelete, onFlash }: { row: any; onSaved: (updated: any) => void; onDelete: (imageId: string) => void; onFlash: (msg: string) => void }) {
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
  }, [row.image_id, row.corrected_label, row.predicted_label, row.comment]);

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
    } catch {
      onFlash("Save failed — check server connection");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!row.feedback_id) {
      onDelete(row.image_id);
      return;
    }
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
        {hoverRect && !imgError ? <HoverPreview src={imgSrc} rect={hoverRect} /> : null}
        <div className="relative">
          <div ref={thumbRef} className="bg-slate-100 flex items-center justify-center h-36 overflow-hidden cursor-zoom-in" onMouseEnter={() => setHoverRect(thumbRef.current?.getBoundingClientRect() ?? null)} onMouseLeave={() => setHoverRect(null)}>
            {!imgError ? <img src={imgSrc} alt={row.filename} className="object-cover h-full w-full hover:scale-105 transition-transform duration-200" loading="lazy" onError={() => setImgError(true)} /> : <div className="text-slate-400 text-xs text-center px-3">Thumbnail unavailable</div>}
          </div>
          <button type="button" onClick={() => { setShowAnnotated((value) => !value); setImgError(false); }} title={showAnnotated ? "Show raw frame" : "Show ONNX detection boxes"} className={`absolute top-1.5 right-1.5 p-1 rounded-md text-xs font-medium shadow transition-colors ${showAnnotated ? "bg-blue-600 text-white" : "bg-white/80 text-slate-600 hover:bg-blue-50"}`}><ScanSearch size={13} /></button>
        </div>
        <div className="p-3 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0"><p className="text-xs font-mono text-slate-600 truncate">{row.filename || "—"}</p><p className="text-xs text-slate-400">{row.capture_date_display || row.capture_date || "—"} · {row.camera_id || "—"}</p></div>
            <Badge color="emerald" size="xs">confirmed</Badge>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-100 rounded-lg px-2.5 py-1.5"><Zap size={12} /><span>Auto-approved — 0 people detected by YOLO</span></div>
        </div>
      </div>
    );
  }

  const yoloConf = row.confidence ? `${Math.round(row.confidence * 100)}%` : "—";
  const isHighConf = (row.confidence || 0) >= 0.65;

  return (
    <div className={`border rounded-2xl bg-white overflow-hidden hover:shadow-md transition-shadow ${row.review_status === "confirmed" ? "border-emerald-200" : row.review_status === "rejected" ? "border-rose-200" : "border-slate-200"}`}>
      {hoverRect && !imgError ? <HoverPreview src={imgSrc} rect={hoverRect} /> : null}
      <div className="relative">
        <div ref={thumbRef} className="bg-slate-100 flex items-center justify-center h-36 overflow-hidden cursor-zoom-in" onMouseEnter={() => setHoverRect(thumbRef.current?.getBoundingClientRect() ?? null)} onMouseLeave={() => setHoverRect(null)}>
          {!imgError ? <img src={imgSrc} alt={row.filename} className="object-cover h-full w-full hover:scale-105 transition-transform duration-200" loading="lazy" onError={() => setImgError(true)} /> : <div className="text-slate-400 text-xs text-center px-3">Thumbnail unavailable</div>}
        </div>
        <button type="button" onClick={() => { setShowAnnotated((value) => !value); setImgError(false); }} title={showAnnotated ? "Show raw frame" : "Show ONNX detection boxes"} className={`absolute top-1.5 right-1.5 p-1 rounded-md shadow transition-colors ${showAnnotated ? "bg-blue-600 text-white" : "bg-white/80 text-slate-600 hover:bg-blue-50"}`}><ScanSearch size={13} /></button>
      </div>
      <div className="p-3 space-y-2.5">
        <div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="text-xs font-mono text-slate-600 truncate">{row.filename || "—"}</p><p className="text-xs text-slate-400">{row.capture_date_display || row.capture_date || "—"} · {row.camera_id || "—"}</p></div><Badge color={statusColor(row.review_status || "pending")}>{row.review_status || "pending"}</Badge></div>
        <div className="rounded-lg border border-slate-200 overflow-hidden">
          <StepHeader icon={<Eye size={11} />} step="Step 1" label="YOLO Detection" color="bg-blue-50 text-blue-700 border-b border-blue-100" />
          <div className="grid grid-cols-2 gap-1.5 p-2"><MetricPill label="People" value={row.person_count ?? 0} /><MetricPill label="Confidence" value={yoloConf} /></div>
          {!isHighConf && (row.person_count ?? 0) > 0 ? <p className="text-[9px] text-amber-600 px-2 pb-1.5">Low YOLO confidence — may be banner or poster</p> : null}
        </div>
        <div className="rounded-lg border border-slate-200 overflow-hidden">
          <StepHeader icon={<Cpu size={11} />} step="Step 2" label="GPT Classification" color="bg-purple-50 text-purple-700 border-b border-purple-100" />
          <div className="p-2 space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap"><span className="text-[10px] text-slate-400">Label:</span><Badge color={predictedColor(row.predicted_label)}>{row.predicted_label || "unknown"}</Badge><Badge color={row.gpt_status === "done" ? "emerald" : row.gpt_status === "failed" ? "rose" : "amber"} size="xs">GPT {row.gpt_status || "pending"}</Badge></div>
            <div className="grid grid-cols-2 gap-1.5"><MetricPill label="Customer" value={row.customer_count ?? 0} /><MetricPill label="Staff" value={row.staff_count ?? 0} /><MetricPill label="Banner" value={row.banner_count ?? 0} /><MetricPill label="Pedestrian" value={row.pedestrian_count ?? 0} /></div>
          </div>
        </div>
        <div>
          <label className="block text-[10px] text-slate-400 mb-1 uppercase tracking-wide">Your Label (correction)</label>
          <select aria-label="Reviewer label correction" className="w-full border rounded-lg px-2.5 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-300" value={corrected} onChange={(e) => setCorrected(e.target.value)}>
            <option value="">Select label</option>
            {LABELS.map((label) => <option key={label} value={label}>{label}</option>)}
          </select>
        </div>
        <textarea className="w-full border rounded-lg px-2.5 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-300 resize-none" placeholder="Why is this correct / incorrect? (optional)" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
        <div className="flex items-center justify-between gap-2">
          <a href={row.drive_link || row.source_url || "#"} target="_blank" rel="noreferrer" className={`text-xs inline-flex items-center gap-1 ${row.drive_link || row.source_url ? "text-blue-600 hover:text-blue-700" : "text-slate-300 pointer-events-none"}`}>Source <ExternalLink size={11} /></a>
          <div className="flex gap-1">
            <button type="button" onClick={() => void save("confirmed")} disabled={saving} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-50"><Check size={11} /> Confirm</button>
            <button type="button" onClick={() => void save("rejected")} disabled={saving} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-50"><X size={11} /> Reject</button>
            <button type="button" onClick={() => void remove()} title="Delete review row" className="p-2 rounded-lg text-slate-400 hover:text-rose-600 border border-slate-200 hover:border-rose-300"><Trash2 size={11} /></button>
          </div>
        </div>
        {row.gpt_error ? <p className="text-[11px] text-rose-500 break-words">{row.gpt_error}</p> : null}
      </div>
    </div>
  );
}
