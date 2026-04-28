import { useEffect, useState } from "react";
import { adminListStores, qaListFeedback, qaUpdateFeedback, qaDeleteFeedback, qaImageUrl } from "../api/client";
import { Card, Title, Text, Badge, Select, SelectItem } from "@tremor/react";
import { Check, X, Trash2, RefreshCw } from "lucide-react";

const LABELS = ["customer", "staff", "passer", "poster_banner", "static_object", "unknown"];

function statusColor(s: string) {
  if (s === "confirmed") return "emerald";
  if (s === "rejected") return "rose";
  return "slate";
}

function FeedbackCard({ row, onUpdate, onDelete }: { row: any; onUpdate: () => void; onDelete: () => void }) {
  const [corrected, setCorrected] = useState(row.corrected_label || row.predicted_label || "");
  const [comment, setComment] = useState(row.comment || "");
  const [saving, setSaving] = useState(false);
  const [imgError, setImgError] = useState(false);

  const imgPath = row.annotated_image_path || row.filename;

  async function approve() {
    setSaving(true);
    try {
      await qaUpdateFeedback(row.id, { review_status: "confirmed", corrected_label: corrected, comment });
      onUpdate();
    } finally { setSaving(false); }
  }

  async function reject() {
    setSaving(true);
    try {
      await qaUpdateFeedback(row.id, { review_status: "rejected", comment });
      onUpdate();
    } finally { setSaving(false); }
  }

  async function remove() {
    if (!confirm("Delete this feedback row?")) return;
    await qaDeleteFeedback(row.id);
    onDelete();
  }

  return (
    <div className={`border rounded-xl bg-white overflow-hidden hover:shadow-sm transition-shadow ${row.review_status === "confirmed" ? "border-emerald-200" : row.review_status === "rejected" ? "border-rose-200" : ""}`}>
      {/* Image */}
      <div className="bg-slate-100 flex items-center justify-center h-40 overflow-hidden">
        {imgPath && !imgError ? (
          <img
            src={qaImageUrl(imgPath)}
            alt={row.filename}
            className="object-cover h-full w-full"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="text-slate-400 text-xs text-center px-2">
            {imgPath ? "Image unavailable" : "No image path"}
          </div>
        )}
      </div>

      {/* Meta */}
      <div className="p-3 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-xs font-mono text-slate-500 truncate max-w-[180px]">{row.filename || "—"}</p>
            <p className="text-xs text-slate-400">{row.capture_date} · {row.camera_id || "—"}</p>
          </div>
          <Badge color={statusColor(row.review_status)}>{row.review_status}</Badge>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-400">Predicted:</span>
          <Badge color="slate">{row.predicted_label || "—"}</Badge>
          {row.confidence ? <span className="text-slate-400">{(row.confidence * 100).toFixed(0)}%</span> : null}
        </div>

        {/* Corrected label */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">Corrected Label</label>
          <select
            className="w-full border rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-300"
            value={corrected}
            onChange={(e) => setCorrected(e.target.value)}
          >
            <option value="">—</option>
            {LABELS.map((l) => <option key={l}>{l}</option>)}
          </select>
        </div>

        <input
          className="w-full border rounded px-2 py-1 text-xs focus:outline-none"
          placeholder="Comment (optional)"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />

        <div className="flex gap-1 pt-1">
          <button
            onClick={approve}
            disabled={saving}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 disabled:opacity-50"
          >
            <Check size={12} /> Confirm
          </button>
          <button
            onClick={reject}
            disabled={saving}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded text-xs bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 disabled:opacity-50"
          >
            <X size={12} /> Reject
          </button>
          <button onClick={remove} className="p-1.5 rounded text-slate-400 hover:text-rose-600 border border-slate-200 hover:border-rose-300">
            <Trash2 size={12} />
          </button>
        </div>
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

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 3000); }

  useEffect(() => {
    adminListStores().then((r) => {
      setStores(r.data);
      if (r.data.length) setStoreId(r.data[0].store_id);
    });
  }, []);

  async function load() {
    setLoading(true);
    qaListFeedback(storeId || undefined, statusFilter || undefined, 300)
      .then((r) => setRows(r.data))
      .finally(() => setLoading(false));
  }

  useEffect(() => { if (storeId !== undefined) load(); }, [storeId, statusFilter]);

  const pending = rows.filter((r) => r.review_status === "pending").length;
  const confirmed = rows.filter((r) => r.review_status === "confirmed").length;
  const rejected = rows.filter((r) => r.review_status === "rejected").length;

  return (
    <div className="space-y-6">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}

      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Title>Frame Review</Title>
          <Text>Review and correct predicted labels on individual frames — builds training data.</Text>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <div className="w-44">
            <Select value={storeId} onValueChange={setStoreId} placeholder="Store">
              {stores.map((s) => <SelectItem key={s.store_id} value={s.store_id}>{s.store_name}</SelectItem>)}
            </Select>
          </div>
          <div className="w-36">
            <Select value={statusFilter} onValueChange={setStatusFilter} placeholder="All Status">
              <SelectItem value="">All</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="confirmed">Confirmed</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </Select>
          </div>
          <button onClick={load} className="p-2 rounded border text-slate-500 hover:text-blue-600 hover:border-blue-400">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Pending</Text><p className="text-2xl font-bold mt-1 text-amber-600">{pending}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Confirmed</Text><p className="text-2xl font-bold mt-1 text-emerald-600">{confirmed}</p></Card>
        <Card className="p-4"><Text className="text-xs uppercase tracking-wide text-slate-400">Rejected</Text><p className="text-2xl font-bold mt-1 text-rose-600">{rejected}</p></Card>
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading frames…</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">
          No QA feedback rows found. Run the on-fly pipeline first to generate frames for review.
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {rows.map((r) => (
            <FeedbackCard
              key={r.id}
              row={r}
              onUpdate={() => { flash("Saved"); load(); }}
              onDelete={() => { flash("Deleted"); load(); }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
