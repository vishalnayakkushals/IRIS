import { useEffect, useState } from "react";
import { fetchWalkins, WalkinSession } from "../api/client";

const ROLE_COLORS: Record<string, string> = {
  customer: "bg-sky-100 text-sky-700",
  staff: "bg-violet-100 text-violet-700",
  manager: "bg-amber-100 text-amber-700",
};

const INCLUDED_COLORS: Record<string, string> = {
  yes: "bg-emerald-100 text-emerald-700",
  no: "bg-rose-100 text-rose-700",
};

type ReviewState = "pending" | "approved" | "rejected";

interface ReviewRow {
  session: WalkinSession;
  review: ReviewState;
}

export default function QualityFeedback() {
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");

  useEffect(() => {
    fetchWalkins(undefined, 100)
      .then((r) => {
        setRows((r.data.sessions || []).map((s) => ({ session: s, review: "pending" })));
      })
      .catch(() => setError("Failed to load walk-in sessions."))
      .finally(() => setLoading(false));
  }, []);

  function setReview(walkinId: string, state: ReviewState) {
    setRows((prev) =>
      prev.map((r) =>
        r.session.walkin_id === walkinId ? { ...r, review: state } : r
      )
    );
  }

  const filtered = filter === "all" ? rows : rows.filter((r) => r.review === filter);
  const counts = {
    pending: rows.filter((r) => r.review === "pending").length,
    approved: rows.filter((r) => r.review === "approved").length,
    rejected: rows.filter((r) => r.review === "rejected").length,
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Quality Assurance Review</h1>
        <p className="text-sm text-slate-500 mt-1">
          Review GPT-analysed walk-in sessions. Approve or reject each detection before model retraining.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4 text-sm">
        {(["pending", "approved", "rejected"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setFilter(filter === s ? "all" : s)}
            className={`border rounded-md px-4 py-3 text-left transition-colors ${
              filter === s ? "border-slate-400 bg-slate-100" : "hover:bg-slate-50"
            }`}
          >
            <p className="text-slate-400 text-xs capitalize mb-1">{s}</p>
            <p className="text-2xl font-bold text-slate-800">{counts[s]}</p>
          </button>
        ))}
      </div>

      {loading && (
        <div className="text-center text-sm text-slate-400 py-12">Loading sessions…</div>
      )}
      {error && <p className="text-rose-600 text-sm">{error}</p>}

      {!loading && !error && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-400">
              Showing {filtered.length} of {rows.length} sessions
            </p>
            {filter !== "all" && (
              <button
                onClick={() => setFilter("all")}
                className="text-xs text-slate-500 hover:text-slate-700 underline"
              >
                Clear filter
              </button>
            )}
          </div>

          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-500 text-left">
                  {["Date", "Store", "Walk-in ID", "Role", "Entry", "Exit", "Time Spent", "Gender", "Analytics", "Actions"].map((h) => (
                    <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={10} className="text-center py-10 text-slate-400">
                      No sessions to review.
                    </td>
                  </tr>
                )}
                {filtered.map(({ session: s, review }) => (
                  <tr
                    key={s.walkin_id}
                    className={`border-t transition-colors ${
                      review === "approved"
                        ? "bg-emerald-50/40"
                        : review === "rejected"
                        ? "bg-rose-50/40"
                        : "hover:bg-slate-50"
                    }`}
                  >
                    <td className="px-3 py-2 whitespace-nowrap">{s.date || "—"}</td>
                    <td className="px-3 py-2 whitespace-nowrap font-mono text-[10px]">{s.store_id}</td>
                    <td className="px-3 py-2 font-mono text-[10px] text-slate-500">{s.walkin_id?.slice(0, 12)}…</td>
                    <td className="px-3 py-2">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-semibold capitalize ${
                          ROLE_COLORS[s.role?.toLowerCase() || ""] ?? "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {s.role || "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{s.entry_time || "—"}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{s.exit_time || "—"}</td>
                    <td className="px-3 py-2">{s.time_spent_mins ? `${s.time_spent_mins}m` : "—"}</td>
                    <td className="px-3 py-2 capitalize">{s.gender || "—"}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-semibold capitalize ${
                          INCLUDED_COLORS[s.included_in_analytics?.toLowerCase() || ""] ??
                          "bg-slate-100 text-slate-400"
                        }`}
                      >
                        {s.included_in_analytics || "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => setReview(s.walkin_id, "approved")}
                          className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                            review === "approved"
                              ? "bg-emerald-600 text-white"
                              : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                          }`}
                        >
                          ✓
                        </button>
                        <button
                          onClick={() => setReview(s.walkin_id, "rejected")}
                          className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                            review === "rejected"
                              ? "bg-rose-600 text-white"
                              : "bg-rose-50 text-rose-700 hover:bg-rose-100"
                          }`}
                        >
                          ✗
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
