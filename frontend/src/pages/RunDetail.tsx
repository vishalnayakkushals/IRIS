import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api, RunRecord } from "../api/client";

type StageStatus = "done" | "running" | "failed" | "skipped" | "idle";

const STAGES = [
  { key: "list", label: "List Images" },
  { key: "skip_check", label: "Skip Check" },
  { key: "download", label: "Download" },
  { key: "yolo", label: "YOLO Detection" },
  { key: "gpt", label: "GPT Analysis" },
  { key: "report", label: "Generate Report" },
  { key: "index", label: "Index Update" },
];

const STATUS_COLORS: Record<StageStatus, string> = {
  done: "bg-emerald-500",
  running: "bg-amber-400 animate-pulse",
  failed: "bg-rose-500",
  skipped: "bg-slate-300",
  idle: "bg-slate-200",
};

const STATUS_LABELS: Record<StageStatus, string> = {
  done: "Done",
  running: "Running",
  failed: "Failed",
  skipped: "Skipped",
  idle: "—",
};

function inferStages(run: RunRecord): { key: string; label: string; status: StageStatus }[] {
  const overall = run.status as string;
  return STAGES.map((stage, idx) => {
    let status: StageStatus = "idle";
    if (overall === "done" || overall === "success") {
      status = "done";
    } else if (overall === "failed") {
      // Mark last stage as failed, earlier ones done, later ones skipped
      if (idx < STAGES.length - 2) status = "done";
      else if (idx === STAGES.length - 2) status = "failed";
      else status = "skipped";
    } else if (overall === "running") {
      status = idx === 3 ? "running" : idx < 3 ? "done" : "idle";
    }
    return { ...stage, status };
  });
}

function fmt(ts: string): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

function elapsed(start: string, end: string): string {
  if (!start || !end) return "—";
  try {
    const ms = new Date(end).getTime() - new Date(start).getTime();
    if (ms < 0) return "—";
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}m ${rem}s`;
  } catch {
    return "—";
  }
}

const STATUS_BADGE: Record<string, string> = {
  done: "bg-emerald-100 text-emerald-700",
  success: "bg-emerald-100 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
  running: "bg-amber-100 text-amber-700",
  queued: "bg-sky-100 text-sky-700",
  idle: "bg-slate-100 text-slate-500",
};

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<RunRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!runId) return;
    api
      .get<RunRecord>(`/runs/${runId}`)
      .then((r) => setRun(r.data))
      .catch(() => setError("Run not found or failed to load."))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
        Loading run…
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-slate-500 hover:text-slate-700 flex items-center gap-1"
        >
          ← Back
        </button>
        <p className="text-rose-600 text-sm">{error || "Run not found."}</p>
      </div>
    );
  }

  const stages = inferStages(run);
  const badgeClass = STATUS_BADGE[run.status] ?? "bg-slate-100 text-slate-500";

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate(-1)}
            className="text-sm text-slate-400 hover:text-slate-600 mb-2 flex items-center gap-1"
          >
            ← Back to runs
          </button>
          <h1 className="text-xl font-semibold text-slate-800">{run.job_name}</h1>
          <p className="text-sm text-slate-500 font-mono mt-0.5">{run.run_id}</p>
        </div>
        <span
          className={`px-2.5 py-1 rounded-full text-xs font-semibold capitalize ${badgeClass}`}
        >
          {run.status}
        </span>
      </div>

      {/* Meta grid */}
      <div className="grid grid-cols-2 gap-4 text-sm">
        {[
          ["Store", run.store_id],
          ["Triggered by", run.triggered_by || "—"],
          ["Started", fmt(run.started_at)],
          ["Completed", fmt(run.completed_at)],
          ["Duration", elapsed(run.started_at, run.completed_at)],
          ["Job key", run.job_key],
        ].map(([label, value]) => (
          <div key={label} className="bg-slate-50 border rounded-md px-4 py-3">
            <p className="text-slate-400 text-xs mb-0.5">{label}</p>
            <p className="font-medium text-slate-800">{value}</p>
          </div>
        ))}
      </div>

      {/* Remarks */}
      {run.remarks && (
        <div className="bg-slate-50 border rounded-md px-4 py-3 text-sm text-slate-700">
          <p className="text-xs text-slate-400 mb-1">Remarks</p>
          {run.remarks}
        </div>
      )}

      {/* Stage timeline */}
      <div>
        <h2 className="text-sm font-semibold text-slate-600 mb-3">Stage Timeline</h2>
        <ol className="relative border-l border-slate-200 ml-3 space-y-6">
          {stages.map((stage) => (
            <li key={stage.key} className="ml-6">
              <span
                className={`absolute -left-2 flex items-center justify-center w-4 h-4 rounded-full ${STATUS_COLORS[stage.status]}`}
              />
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-700">{stage.label}</p>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    stage.status === "done"
                      ? "bg-emerald-50 text-emerald-700"
                      : stage.status === "failed"
                      ? "bg-rose-50 text-rose-700"
                      : stage.status === "running"
                      ? "bg-amber-50 text-amber-700"
                      : "bg-slate-50 text-slate-400"
                  }`}
                >
                  {STATUS_LABELS[stage.status]}
                </span>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
