import { useEffect, useState } from "react";
import { Title, Text, Metric, Card, Grid, Badge } from "@tremor/react";
import { fetchStoreMetrics, fetchWalkins, fetchAnalytics, WalkinSession } from "../api/client";
import { useStore } from "../context/StoreContext";

const ROLE_COLOR: Record<string, "rose" | "blue" | "gray"> = {
  CUSTOMER: "blue",
  STAFF: "rose",
};
const ENTRY_COLOR: Record<string, "emerald" | "gray"> = {
  BILLING: "emerald",
};

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100, 200];

export default function StoreDetail() {
  const { storeId, stores } = useStore();
  const [metrics, setMetrics] = useState<{ footfall: number | string; bounce_rate: string; dwell_time: string; status: string } | null>(null);
  const [sessions, setSessions] = useState<WalkinSession[]>([]);
  const [sessionPage, setSessionPage] = useState(1);
  const [sessionPageSize, setSessionPageSize] = useState(10);
  const [loadingMetrics, setLoadingMetrics] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);

  useEffect(() => {
    setLoadingMetrics(true);
    setLoadingSessions(true);
    setMetrics(null);
    setSessions([]);
    setSessionPage(1);

    if (storeId) {
      // Per-store: use dedicated metrics + walkins endpoints
      fetchStoreMetrics(storeId)
        .then((res) => setMetrics(res.data ?? null))
        .catch(() => {})
        .finally(() => setLoadingMetrics(false));

      fetchWalkins(storeId, 500)
        .then((res) => { setSessions(res.data?.sessions ?? []); setSessionPage(1); })
        .catch(() => {})
        .finally(() => setLoadingSessions(false));
    } else {
      // All stores: use analytics aggregate for KPIs, walkins without store filter
      fetchAnalytics(undefined, { days: 30 })
        .then((res) => {
          const d = res.data;
          if (d) {
            setMetrics({
              footfall: d.total_walkins ?? 0,
              bounce_rate: `${d.conversion_rate ?? 0}% conv.`,
              dwell_time: `${d.avg_dwell_mins ?? 0} min`,
              status: "",
            });
          }
        })
        .catch(() => {})
        .finally(() => setLoadingMetrics(false));

      fetchWalkins(undefined, 500)
        .then((res) => { setSessions(res.data?.sessions ?? []); setSessionPage(1); })
        .catch(() => {})
        .finally(() => setLoadingSessions(false));
    }
  }, [storeId]);

  const selectedStore = stores.find((s) => s.store_id === storeId);
  const pageTitle = storeId ? (selectedStore?.store_name ?? storeId) : "All Stores";

  return (
    <div className="space-y-6 animate-in fade-in zoom-in duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <Title>Store Detail</Title>
          <Text>{pageTitle}</Text>
        </div>
      </div>

      <Grid numItemsSm={1} numItemsLg={3} className="gap-6">
        <Card decoration="top" decorationColor="indigo">
          <Text>{storeId ? "Daily Footfall" : "Total Walk-ins (30d)"}</Text>
          <Metric>{loadingMetrics ? "—" : (metrics?.footfall ?? 0)}</Metric>
        </Card>
        <Card decoration="top" decorationColor="rose">
          <Text>{storeId ? "Bounce Rate" : "Conversion Rate"}</Text>
          <Metric>{loadingMetrics ? "—" : (metrics?.bounce_rate ?? "—")}</Metric>
        </Card>
        <Card decoration="top" decorationColor="amber">
          <Text>Avg Dwell Time</Text>
          <Metric>{loadingMetrics ? "—" : (metrics?.dwell_time ?? "—")}</Metric>
        </Card>
      </Grid>

      <Card>
        <div className="flex items-center justify-between mb-4">
          <Title>Walk-in Sessions</Title>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span>Rows per page:</span>
            <select
              value={sessionPageSize}
              onChange={(e) => { setSessionPageSize(Number(e.target.value)); setSessionPage(1); }}
              className="border border-slate-200 rounded px-2 py-1 text-xs bg-white"
            >
              {PAGE_SIZE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            {sessions.length > 0 && (
              <span className="text-slate-400">
                {((sessionPage - 1) * sessionPageSize) + 1}–{Math.min(sessionPage * sessionPageSize, sessions.length)} of {sessions.length.toLocaleString()}
              </span>
            )}
          </div>
        </div>
        {loadingSessions ? (
          <Text className="mt-4 text-slate-400">Loading sessions…</Text>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b text-slate-500 text-xs uppercase">
                    <th className="pb-2 pr-4">Walk-in ID</th>
                    <th className="pb-2 pr-4">Date</th>
                    <th className="pb-2 pr-4">Store</th>
                    <th className="pb-2 pr-4">Role</th>
                    <th className="pb-2 pr-4">Entry</th>
                    <th className="pb-2 pr-4">Exit</th>
                    <th className="pb-2 pr-4">Dwell (min)</th>
                    <th className="pb-2 pr-4">Entry Type</th>
                    <th className="pb-2 pr-4">Gender</th>
                    <th className="pb-2 pr-4">Age Band</th>
                    <th className="pb-2 pr-4">Style</th>
                    <th className="pb-2 pr-4">Engagement</th>
                    <th className="pb-2 pr-4">Purchase Signal</th>
                    <th className="pb-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.length === 0 ? (
                    <tr>
                      <td colSpan={14} className="py-10 text-center text-slate-400">
                        No walk-in sessions recorded yet{storeId ? ` for ${pageTitle}` : ""}. Run a sync to populate this table.
                      </td>
                    </tr>
                  ) : (
                    sessions.slice((sessionPage - 1) * sessionPageSize, sessionPage * sessionPageSize).map((s) => (
                      <tr key={s.id} className="border-b last:border-0 hover:bg-slate-50">
                        <td className="py-2 pr-4 font-mono text-xs text-slate-600">{s.walkin_id || "—"}</td>
                        <td className="py-2 pr-4">{s.date || "—"}</td>
                        <td className="py-2 pr-4 text-xs text-slate-500">{s.store_id || "—"}</td>
                        <td className="py-2 pr-4">
                          <Badge color={ROLE_COLOR[s.role?.toUpperCase()] ?? "gray"} size="xs">
                            {s.role || "—"}
                          </Badge>
                        </td>
                        <td className="py-2 pr-4 text-xs">{s.entry_time || "—"}</td>
                        <td className="py-2 pr-4 text-xs">{s.exit_time || "—"}</td>
                        <td className="py-2 pr-4">{s.time_spent_mins || "—"}</td>
                        <td className="py-2 pr-4">
                          <Badge color={ENTRY_COLOR[s.entry_type?.toUpperCase()] ?? "gray"} size="xs">
                            {s.entry_type || "—"}
                          </Badge>
                        </td>
                        <td className="py-2 pr-4">{s.gender || "—"}</td>
                        <td className="py-2 pr-4">{s.age_band || "—"}</td>
                        <td className="py-2 pr-4 text-xs">{s.clothing_style_archetype || "—"}</td>
                        <td className="py-2 pr-4 text-xs">{s.engagement_type || "—"}</td>
                        <td className="py-2 pr-4 text-xs">{s.purchase_signal_bag || "—"}</td>
                        <td className="py-2">
                          <Badge color={s.session_status === "closed" ? "emerald" : "amber"} size="xs">
                            {s.session_status || "—"}
                          </Badge>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {sessions.length > sessionPageSize && (
              <div className="flex items-center justify-center gap-2 mt-4 text-xs">
                <button
                  onClick={() => setSessionPage((p) => Math.max(1, p - 1))}
                  disabled={sessionPage === 1}
                  className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >
                  ← Prev
                </button>
                <span className="text-slate-500">Page {sessionPage} / {Math.ceil(sessions.length / sessionPageSize)}</span>
                <button
                  onClick={() => setSessionPage((p) => Math.min(Math.ceil(sessions.length / sessionPageSize), p + 1))}
                  disabled={sessionPage >= Math.ceil(sessions.length / sessionPageSize)}
                  className="px-3 py-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
