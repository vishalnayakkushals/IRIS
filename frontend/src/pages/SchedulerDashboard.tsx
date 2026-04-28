import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getJobs, getRuns, triggerAll, triggerJob } from "../api/client";
import type { JobStatus, RunRecord } from "../api/client";
import JobTable from "../components/JobTable";
import { Play } from "lucide-react";
import { Card, Title, Text, Badge, TabList, Tab, TabGroup, TabPanels, TabPanel, Button } from "@tremor/react";

const POLL_MS = 5000;
const ACTIVE = new Set(["running", "queued"]);

function hasActiveJobs(jobs: JobStatus[]) {
  return jobs.some((j) => ACTIVE.has(j.status));
}

export default function SchedulerDashboard() {
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [toast, setToast] = useState("");
  const [scanning, setScanning] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const { data } = await getJobs();
      setJobs(data);
    } catch {
      // silent
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

  useEffect(() => {
    loadJobs();
    loadRuns();
  }, [loadJobs, loadRuns]);

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      loadJobs();
      loadRuns();
    }, POLL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [loadJobs, loadRuns]);

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
      showToast("Failed to trigger pipeline");
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

  const anyActive = hasActiveJobs(jobs);

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toast && (
        <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg opacity-90 transition-opacity">
          {toast}
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <Title>Pipeline Scheduler</Title>
          <Text>Manage, trigger, and review background pipeline stages.</Text>
        </div>
        <Button
          icon={Play}
          size="sm"
          color="blue"
          onClick={handleScanAll}
          disabled={scanning || anyActive}
          loading={scanning}
          loadingText="Running..."
        >
          {anyActive ? "Running..." : "Scan Now"}
        </Button>
      </div>

      <TabGroup>
        <TabList className="mt-4">
          <Tab>Manual Sync</Tab>
          <Tab>Run History</Tab>
        </TabList>
        <TabPanels>
          {/* Manual Sync Tab */}
          <TabPanel>
            <Card className="mt-6">
              <div className="flex items-center justify-between mb-4">
                <Title>Active Queue Status</Title>
                <Text className="text-xs">Auto-refreshes every 5 seconds</Text>
              </div>
              {jobs.length === 0 ? (
                <div className="text-center py-8 text-gray-400 text-sm">Loading pipeline status…</div>
              ) : (
                <JobTable jobs={jobs} onTrigger={handleTriggerJob} />
              )}
            </Card>
          </TabPanel>

          {/* Run History Tab */}
          <TabPanel>
            <Card className="mt-6 p-0 border-0 shadow-sm ring-1 ring-slate-200 rounded-lg overflow-hidden">
              <div className="p-4 border-b">
                 <Title>Recent Executions</Title>
              </div>
              {runs.length === 0 ? (
                <div className="text-center py-12 text-gray-400 text-sm">No runs recorded.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm whitespace-nowrap">
                    <thead>
                      <tr className="bg-slate-50 border-b text-slate-500 font-semibold text-xs tracking-wider uppercase">
                        <th className="px-6 py-3">Job</th>
                        <th className="px-6 py-3">Status</th>
                        <th className="px-6 py-3">Remarks</th>
                        <th className="px-6 py-3">Triggered By</th>
                        <th className="px-6 py-3">Started</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {runs.map((r) => (
                        <tr key={r.run_id} className="hover:bg-slate-50/50 transition-colors">
                          <td className="px-6 py-4 font-medium text-slate-700">
                            <Link
                              to={`/runs/${r.run_id}`}
                              className="hover:text-blue-600 hover:underline"
                            >
                              {r.job_name}
                            </Link>
                          </td>
                          <td className="px-6 py-4">
                            <Badge
                              color={
                                r.status === "done" ? "emerald" :
                                r.status === "failed" ? "rose" :
                                r.status === "running" ? "amber" : "slate"
                              }
                            >
                              {r.status}
                            </Badge>
                          </td>
                          <td className="px-6 py-4 text-slate-500 max-w-xs truncate">{r.remarks || "—"}</td>
                          <td className="px-6 py-4 text-slate-500">{r.triggered_by}</td>
                          <td className="px-6 py-4 text-slate-400 text-xs">
                            {r.started_at
                              ? new Date(r.started_at).toLocaleString("en-IN", { hour12: true })
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </TabPanel>
        </TabPanels>
      </TabGroup>
    </div>
  );
}
