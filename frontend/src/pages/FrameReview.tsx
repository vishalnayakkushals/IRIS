import { useEffect, useMemo, useState } from "react";
import {
  adminListStores,
  qaReviewQueue,
  qaCreateFeedback,
  qaUpdateFeedback,
  qaDeleteFeedback,
  qaFrameImageUrl,
} from "../api/client";
import { Card, Title, Text, Badge, Select, SelectItem } from "@tremor/react";
import { Check, X, Trash2, RefreshCw, ExternalLink, ChevronLeft, ChevronRight } from "lucide-react";
import StoreSelect from "../components/StoreSelect";

const LABELS = ["customer", "staff", "banner", "pedestrian", "unknown"];
const PAGE_SIZE = 24;

function statusColor(s: string) {
  if (s === "confirmed") return "emerald";
  if (s === "rejected") return "rose";
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

function MetricPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-slate-50 px-2.5 py-1.5 border border-slate-200">
      <p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className="text-sm font-semibold text-slate-700">{value}</p>
    </div>
  );
}

function FeedbackCard({
  row,
  onUpdate,
  onDelete,
}: {
  row: any;
  onUpdate: () => void;
  onDelete: () => void;
}) {
  const [corrected, setCorrected] = useState(row.corrected_label || row.predicted_label || "");
  const [comment, setComment] = useState(row.comment || "");
  const [saving, setSaving] = useState(false);
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    setCorrected(row.corrected_label || row.predicted_label || "");
    setComment(row.comment || "");
    setImgError(false);
  }, [row]);

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
      onUpdate();
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!row.feedback_id) { onDelete(); return; }
    if (!confirm("Delete this review row?")) return;
    await qaDeleteFeedback(row.feedback_id);
    onDelete();
  }

  return (
    <div className={`border rounded-2xl bg-white overflow-hidden hover:shadow-md transition-shadow ${row.review_status === "confirmed" ? "border-emerald-200" : row.review_status === "rejected" ? "border-rose-200" : "border-slate-200"}`}>
      <div className="bg-slate-100 flex items-center justify-center h-44 overflow-hidden">
        {!imgError ? (
          <img
            src={qaFrameImageUrl(row.store_id, row.image_id)}
            alt={row.filename}
            className="object-cover h-full w-full"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="text-slate-400 text-xs text-center px-3">Thumbnail unavailable</div>
        )}
      </div>

      <div className="p-3 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-mono text-slate-600 truncate">{row.filename || "—"}</p>
            <p className="text-xs text-slate-400">{row.capture_date_display || row.capture_date || "—"} · {row.camera_id || "—"}</p>
          </div>
          <Badge color={statusColor(row.review_status || "pending")}>{row.review_status || "pending"}</Badge>
        </div>

        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span className="text-slate-400">Predicted:</span>
          <Badge color={predictedColor(row.predicted_label)}>{row.predicted_label || "unknown"}</Badge>
          <Badge color={row.gpt_status === "done" ? "emerald" : row.gpt_status === "failed" ? "rose" : "amber"}>
            GPT {row.gpt_status || "pending"}
          </Badge>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <MetricPill label="YOLO People" value={row.person_count ?? 0} />
          <MetricPill label="Customer" value={row.customer_count ?? 0} />
          <MetricPill label="Staff" value={row.staff_count ?? 0} />
          <MetricPill label="Banner/Ped" value={`${row.banner_count ?? 0}/${row.pedestrian_count ?? 0}`} />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Reviewer Label</label>
          <select
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
          placeholder="Why is this correct / incorrect?"
          rows={2}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />

        <div className="flex items-center justify-between gap-2">
          <a
            href={row.drive_link || row.source_url || "#"}
            target="_blank"
            rel="noreferrer"
            className={`text-xs inline-flex items-center gap-1 ${row.drive_link || row.source_url ? "text-blue-600 hover:text-blue-700" : "text-slate-300 pointer-events-none"}`}
          >
            Open Source <ExternalLink size={12} />
          </a>
          <div className="flex gap-1">
            <button
              onClick={() => save("confirmed")}
              disabled={saving}
              className="flex items-center justify-center gap-1 px-2.5 py-1.5 rounded-lg text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-50"
            >
              <Check size={12} /> Confirm
            </button>
            <button
              onClick={() => save("rejected")}
              disabled={saving}
              className="flex items-center justify-center gap-1 px-2.5 py-1.5 rounded-lg text-xs bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-50"
            >
              <X size={12} /> Reject
            </button>
            <button
              onClick={remove}
              className="p-2 rounded-lg text-slate-400 hover:text-rose-600 border border-slate-200 hover:border-rose-300"
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>

        {row.gpt_error ? <p className="text-[11px] text-rose-500 break-words">{row.gpt_error}</p> : null}
      </div>
    </div>
  );
}

export default function FrameReview() {
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [page, setPage] = useState(0);

  function flash(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  }

  useEffect(() => {
    adminListStores().then((r) => {
      setStores(r.data);
      if (r.data.length) setStoreId(r.data[0].store_id);
    });
  }, []);

  async function load() {
    if (!storeId) return;
    setLoading(true);
    setPage(0);
    qaReviewQueue(storeId, statusFilter || undefined, dateFilter || undefined, 300)
      .then((r) => setRows(r.data))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (storeId) void load();
  }, [storeId, statusFilter, dateFilter]);

  const dateOptions = useMemo(
    () => Array.from(new Set(rows.map((r) => r.capture_date).filter(Boolean))).sort().reverse(),
    [rows],
  );

  const pending   = rows.filter((r) => (r.review_status || "pending") === "pending").length;
  const confirmed = rows.filter((r) => r.review_status === "confirmed").length;
  const rejected  = rows.filter((r) => r.review_status === "rejected").length;

  const totalPages = Math.ceil(rows.length / PAGE_SIZE);
  const pageRows   = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="space-y-6">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}

      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Title>Frame Review</Title>
          <Text>Review frame thumbnails, confirm customer/staff/banner/pedestrian labels, feed decisions into correction memory.</Text>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <div className="w-72">
            <StoreSelect stores={stores} value={storeId} onChange={setStoreId} placeholder="Filter review by store" />
          </div>
          <div className="w-40">
            <Select value={statusFilter} onValueChange={setStatusFilter} placeholder="All Status">
              <SelectItem value="">All</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="confirmed">Confirmed</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </Select>
          </div>
          <div className="w-40">
            <Select value={dateFilter} onValueChange={setDateFilter} placeholder="All Dates">
              <SelectItem value="">All Dates</SelectItem>
              {dateOptions.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
            </Select>
          </div>
          <button onClick={() => void load()} className="p-2 rounded border text-slate-500 hover:text-blue-600 hover:border-blue-400">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Pending</Text><p className="text-2xl font-bold mt-1 text-amber-600">{pending}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Confirmed</Text><p className="text-2xl font-bold mt-1 text-emerald-600">{confirmed}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Rejected</Text><p className="text-2xl font-bold mt-1 text-rose-600">{rejected}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Total Loaded</Text><p className="text-2xl font-bold mt-1 text-slate-700">{rows.length}</p></Card>
      </div>

      <Card className="p-5 bg-slate-50">
        <p className="font-semibold text-slate-700 mb-2 text-sm">How this review feeds GPT learning</p>
        <ol className="space-y-1.5 text-sm text-slate-600 list-decimal list-inside">
          <li>Review the frame thumbnail and compare it with the generated counts.</li>
          <li>Mark the dominant frame label as customer, staff, banner, or pedestrian.</li>
          <li>Confirmed labels are stored in QA feedback and become available to the correction-memory / retrain flow.</li>
        </ol>
      </Card>

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading frames…</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">
          No review rows found. Run the pipeline first, or change filters.
        </div>
      ) : (
        <>
          {/* Pagination bar */}
          <div className="flex items-center justify-between text-sm text-slate-500">
            <span>Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, rows.length)} of {rows.length} frames</span>
            <div className="flex items-center gap-2">
              <button
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
                className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100"
              >
                <ChevronLeft size={16} />
              </button>
              <span>Page {page + 1} / {totalPages}</span>
              <button
                disabled={page >= totalPages - 1}
                onClick={() => setPage(p => p + 1)}
                className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
            {pageRows.map((r) => (
              <FeedbackCard
                key={`${r.store_id}:${r.image_id}`}
                row={r}
                onUpdate={() => { flash("Review saved"); void load(); }}
                onDelete={() => { flash("Review updated"); void load(); }}
              />
            ))}
          </div>

          {/* Bottom pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2">
              <button disabled={page === 0} onClick={() => { setPage(p => p - 1); window.scrollTo(0, 0); }} className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100">
                <ChevronLeft size={16} />
              </button>
              {Array.from({ length: Math.min(totalPages, 10) }, (_, i) => (
                <button
                  key={i}
                  onClick={() => { setPage(i); window.scrollTo(0, 0); }}
                  className={`w-8 h-8 rounded text-sm ${page === i ? "bg-blue-600 text-white" : "border hover:bg-slate-50 text-slate-600"}`}
                >
                  {i + 1}
                </button>
              ))}
              <button disabled={page >= totalPages - 1} onClick={() => { setPage(p => p + 1); window.scrollTo(0, 0); }} className="p-1.5 rounded border disabled:opacity-30 hover:bg-slate-100">
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
