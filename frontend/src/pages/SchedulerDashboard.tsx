import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getJobs, getRuns, triggerAll, triggerJob } from "../api/client";
import type { JobStatus, RunRecord } from "../api/client";
import JobTable from "../components/JobTable";

const POLL_MS = 5000;
const ACTIVE = new Set(["running", "queued"]);

function hasActiveJobs(jobs: JobStatus[]) {
  return jobs.some((j) => ACTIVE.has(j.status));
}

export default function SchedulerDashboard() {
  const [tab, setTab] = useState<"manual" | "history">("manual");
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [toast, setToast] = useState("");
  const [scanning, setScanning] = useState(false);
  const navigate = useNavigate();
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const { data } = await getJobs();
      setJobs(data);
    } catch {
      // silent — will retry
    }
  }, []);

  const loadRuns = useCallback(async () => {
    try {
      const { data } = await getRuns(20);
      setRuns(data.runs);
    } catch {
      // silent
    }
  }, []);

  // Start/stop polling based on whether jobs are active
  useEffect(() => {
    loadJobs();
    if (tab === "history") loadRuns();
  }, [tab, loadJobs, loadRuns]);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      loadJobs();
      if (tab === "history") loadRuns();
    }, POLL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [tab, loadJobs, loadRuns]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 4000);
  }

  async function handleScanAll() {
    setScanning(true);
    try {
      const { data } = await triggerAll();
      showToast(data.message || "Full pipeline queued");
      await loadJobs();
    } catch {
      showToast("Failed to trigger pipeline. Check API.");
    } finally {
      setScanning(false);
    }
  }

  async function handleTriggerJob(key: string) {
    try {
      const { data } = await triggerJob(key);
      showToast(data.message || `${key} queued`);
      await loadJobs();
    } catch {
      showToast(`Failed to trigger ${key}`);
    }
  }

  function handleLogout() {
    localStorage.removeItem("iris_token");
    navigate("/login");
  }

  const anyActive = hasActiveJobs(jobs);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <span className="text-white text-sm font-bold">I</span>
          </div>
          <span className="font-semibold text-gray-800 text-lg">IRIS</span>
          <span className="text-gray-400 text-sm ml-2">Retail Intelligence</span>
        </div>
        <button
          onClick={handleLogout}
          className="text-sm text-gray-500 hover:text-gray-800 transition-colors"
        >
          Sign out
        </button>
      </header>

      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-gray-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">
          {toast}
        </div>
      )}

      <main className="max-w-6xl mx-auto px-6 py-8">
        {/* Page title + Scan Now button */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-gray-800">Pipeline Scheduler</h2>
            <p className="text-gray-500 text-sm mt-0.5">
              TEST_STORE_D07 — Drive → YOLO → GPT → Report
            </p>
          </div>
          <button
            onClick={handleScanAll}
            disabled={scanning || anyActive}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"
          >
            {scanning || anyActive ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Running…
              </>
            ) : (
              "▶ Scan Now"
            )}
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-0 mb-6 border-b border-gray-200">
          {(["manual", "history"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t === "manual" ? (
                <span className="flex items-center gap-1.5">
                  <span>🔄</span> Manual Sync
                </span>
              ) : (
                <span className="flex items-center gap-1.5">
                  <span>📋</span> Run History
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Manual Sync tab */}
        {tab === "manual" && (
          <>
            {jobs.length === 0 ? (
              <div className="text-center py-12 text-gray-400">Loading pipeline status…</div>
            ) : (
              <JobTable jobs={jobs} onTrigger={handleTriggerJob} />
            )}
            <p className="text-xs text-gray-400 mt-4">
              Auto-refreshes every 5 seconds. YOLO scan runs hourly; full pipeline runs at midnight IST.
            </p>
          </>
        )}

        {/* Run History tab */}
        {tab === "history" && (
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
            {runs.length === 0 ? (
              <div className="text-center py-12 text-gray-400">No runs yet. Click "Scan Now" to start.</div>
            ) : (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase">Job</th>
                    <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase">Status</th>
                    <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase">Remarks</th>
                    <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase">Triggered By</th>
                    <th className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase">Started</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.run_id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="px-5 py-3 font-medium text-gray-700">{r.job_name}</td>
                      <td className="px-5 py-3">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${
                            r.status === "done"
                              ? "bg-green-100 text-green-700"
                              : r.status === "failed"
                              ? "bg-red-100 text-red-700"
                              : r.status === "running"
                              ? "bg-orange-100 text-orange-700"
                              : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {r.status}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-gray-600 max-w-xs truncate">{r.remarks || "—"}</td>
                      <td className="px-5 py-3 text-gray-500">{r.triggered_by}</td>
                      <td className="px-5 py-3 text-gray-500">
                        {r.started_at
                          ? new Date(r.started_at).toLocaleString("en-IN", { hour12: true })
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
