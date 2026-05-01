import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Title, Text, Metric, Card, Grid, BarChart, LineChart, DonutChart, Badge,
} from "@tremor/react";
import {
  fetchAnalytics, fetchTrend, fetchLeaderboard, fetchDelta,
  listStores, StoreOption,
  AnalyticsData, TrendPoint, LeaderboardRow, DeltaData,
} from "../api/client";
import StoreSelect from "../components/StoreSelect";

const DAY_OPTIONS = [7, 30, 90];
const GROUP_OPTIONS: { label: string; value: string }[] = [
  { label: "Day", value: "day" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
];

function DeltaBadge({ pct }: { pct: number }) {
  if (pct === 0) return <Badge color="gray">—</Badge>;
  return (
    <Badge color={pct > 0 ? "emerald" : "red"}>
      {pct > 0 ? "▲" : "▼"} {Math.abs(pct)}%
    </Badge>
  );
}

export default function Overview() {
  const [stores, setStores] = useState<StoreOption[]>([]);
  const [storeFilter, setStoreFilter] = useState("");
  const [days, setDays] = useState(30);
  const [groupBy, setGroupBy] = useState("day");

  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [delta, setDelta] = useState<DeltaData | null>(null);
  const [loading, setLoading] = useState(false);
  const [hasSelected, setHasSelected] = useState(false); // blank first — wait for explicit store selection

  useEffect(() => {
    listStores()
      .then((res) => setStores(res.data?.stores ?? []))
      .catch(() => {});
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    const sid = storeFilter || undefined;
    Promise.all([
      fetchAnalytics(sid, days),
      fetchTrend(sid, days, groupBy),
      fetchLeaderboard(days),
      fetchDelta(sid, days, days),
    ])
      .then(([a, t, l, d]) => {
        setAnalytics(a.data);
        setTrend(t.data ?? []);
        setLeaderboard(l.data ?? []);
        setDelta(d.data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [storeFilter, days, groupBy]);

  useEffect(() => {
    if (hasSelected) load();
  }, [load, hasSelected]);

  const trendData = useMemo(() => trend.map((p) => ({
    period: p.period,
    "Walk-ins": p.walkins,
    Conversions: p.conversions,
    "Avg Dwell (min)": p.avg_dwell,
  })), [trend]);

  const genderData = useMemo(() => (analytics?.gender ?? []).map((g) => ({
    name: g.label,
    value: g.value,
  })), [analytics?.gender]);

  const ageData = useMemo(() => (analytics?.age_bands ?? []).map((a) => ({
    name: a.label,
    value: a.value,
  })), [analytics?.age_bands]);

  return (
    <div className="space-y-6 animate-in fade-in zoom-in duration-500">
      {/* Header row */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <Title>Business Overview</Title>
          <Text>Walk-in, conversion and engagement analytics from the pipeline.</Text>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          {/* Day-range selector */}
          <div className="flex rounded-lg overflow-hidden border border-slate-200 text-sm">
            {DAY_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 ${days === d ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
              >
                {d}d
              </button>
            ))}
          </div>
          {stores.length > 0 && (
            <StoreSelect
              stores={stores}
              value={storeFilter}
              onChange={(v) => { setHasSelected(true); setStoreFilter(v); }}
              includeAll
              allLabel="All Stores"
              placeholder="Select a store to load…"
              className="w-52"
            />
          )}
        </div>
      </div>

      {/* Empty state — shown until user selects a store */}
      {!hasSelected && (
        <Card className="p-12 text-center space-y-2">
          <p className="text-slate-500 text-sm font-medium">Select a store to view analytics.</p>
          <p className="text-slate-400 text-xs">Choose a store or "All Stores" from the selector above. Data loads only after selection.</p>
        </Card>
      )}

      {/* KPI cards, charts, leaderboard — shown only after explicit store selection */}
      {hasSelected && <><Grid numItemsSm={2} numItemsLg={4} className="gap-4">
        <Card decoration="top" decorationColor="blue">
          <div className="flex items-start justify-between">
            <Text>Walk-ins</Text>
            {delta && <DeltaBadge pct={delta.delta_walkins_pct} />}
          </div>
          <Metric className="mt-1">{loading ? "—" : (analytics?.total_walkins ?? 0).toLocaleString()}</Metric>
          <Text className="text-xs text-slate-400 mt-1">Groups: {analytics?.total_groups ?? 0}</Text>
        </Card>
        <Card decoration="top" decorationColor="emerald">
          <div className="flex items-start justify-between">
            <Text>Conversions</Text>
            {delta && <DeltaBadge pct={delta.delta_conversions_pct} />}
          </div>
          <Metric className="mt-1">{loading ? "—" : (analytics?.total_conversions ?? 0).toLocaleString()}</Metric>
          <Text className="text-xs text-slate-400 mt-1">Out of {analytics?.total_walkins ?? 0} walk-ins</Text>
        </Card>
        <Card decoration="top" decorationColor="amber">
          <div className="flex items-start justify-between">
            <Text>Conversion Rate</Text>
            {delta && <DeltaBadge pct={delta.delta_rate_pct} />}
          </div>
          <Metric className="mt-1">{loading ? "—" : `${analytics?.conversion_rate ?? 0}%`}</Metric>
          <Text className="text-xs text-slate-400 mt-1">Last {days} days</Text>
        </Card>
        <Card decoration="top" decorationColor="indigo">
          <Text>Avg Dwell Time</Text>
          <Metric className="mt-1">{loading ? "—" : `${analytics?.avg_dwell_mins ?? 0} min`}</Metric>
          <Text className="text-xs text-slate-400 mt-1">Staff: {analytics?.total_staff ?? 0}</Text>
        </Card>
      </Grid>

      {/* Trend chart */}
      <Card>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
          <Title>Trend — Walk-ins &amp; Conversions</Title>
          <div className="flex rounded-lg overflow-hidden border border-slate-200 text-sm">
            {GROUP_OPTIONS.map((g) => (
              <button
                key={g.value}
                onClick={() => setGroupBy(g.value)}
                className={`px-3 py-1.5 ${groupBy === g.value ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>
        {!loading && trendData.length === 0 ? (
          <div className="h-56 flex items-center justify-center text-slate-400 bg-slate-50/50 rounded-lg border border-dashed text-sm">
            No trend data yet. Run the pipeline to populate this chart.
          </div>
        ) : (
          <LineChart
            className="mt-2 h-56"
            data={trendData}
            index="period"
            categories={["Walk-ins", "Conversions"]}
            colors={["blue", "emerald"]}
            showLegend
            yAxisWidth={40}
          />
        )}
      </Card>

      {/* Gender + Age breakdowns */}
      <Grid numItemsSm={1} numItemsLg={2} className="gap-4">
        <Card>
          <Title>Gender Breakdown</Title>
          {genderData.length === 0 ? (
            <div className="h-40 flex items-center justify-center text-slate-400 text-sm">No data</div>
          ) : (
            <div className="flex items-center gap-6 mt-4">
              <DonutChart
                className="h-36 w-36"
                data={genderData}
                category="value"
                index="name"
                colors={["blue", "rose", "amber", "gray"]}
              />
              <div className="space-y-2">
                {genderData.map((g, i) => {
                  const colors = ["bg-blue-500", "bg-rose-500", "bg-amber-500", "bg-gray-400"];
                  const total = genderData.reduce((s, x) => s + x.value, 0);
                  return (
                    <div key={g.name} className="flex items-center gap-2 text-sm">
                      <span className={`w-3 h-3 rounded-full ${colors[i % colors.length]}`} />
                      <span className="text-slate-700 capitalize">{g.name.toLowerCase()}</span>
                      <span className="text-slate-400 ml-auto pl-4">{g.value} ({total ? Math.round(g.value / total * 100) : 0}%)</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Card>
        <Card>
          <Title>Age Band Breakdown</Title>
          {ageData.length === 0 ? (
            <div className="h-40 flex items-center justify-center text-slate-400 text-sm">No data</div>
          ) : (
            <BarChart
              className="mt-2 h-40"
              data={ageData}
              index="name"
              categories={["value"]}
              colors={["violet"]}
              showLegend={false}
              yAxisWidth={36}
            />
          )}
        </Card>
      </Grid>

      {/* Engagement breakdown */}
      {(analytics?.engagement ?? []).length > 0 && (
        <Card>
          <Title>Engagement Types</Title>
          <BarChart
            className="mt-4 h-48"
            data={(analytics?.engagement ?? []).map((e) => ({ name: e.label, Customers: e.value }))}
            index="name"
            categories={["Customers"]}
            colors={["teal"]}
            showLegend={false}
            yAxisWidth={36}
            layout="vertical"
          />
        </Card>
      )}

      {/* Store Leaderboard */}
      {leaderboard.length > 0 && (
        <Card>
          <Title>Store Leaderboard — Last {days} Days</Title>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-100">
                  <th className="pb-2 font-medium">#</th>
                  <th className="pb-2 font-medium">Store</th>
                  <th className="pb-2 font-medium text-right">Walk-ins</th>
                  <th className="pb-2 font-medium text-right">Groups</th>
                  <th className="pb-2 font-medium text-right">Conversions</th>
                  <th className="pb-2 font-medium text-right">Conv. Rate</th>
                  <th className="pb-2 font-medium text-right">Avg Dwell</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((row, idx) => (
                  <tr key={row.store_id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                    <td className="py-2 text-slate-400">{idx + 1}</td>
                    <td className="py-2 font-medium text-slate-800">{row.store_name}</td>
                    <td className="py-2 text-right">{row.walkins.toLocaleString()}</td>
                    <td className="py-2 text-right text-slate-500">{row.groups.toLocaleString()}</td>
                    <td className="py-2 text-right text-emerald-700">{row.conversions.toLocaleString()}</td>
                    <td className="py-2 text-right">
                      <span className={`font-semibold ${row.conversion_rate >= 20 ? "text-emerald-600" : row.conversion_rate >= 10 ? "text-amber-600" : "text-red-500"}`}>
                        {row.conversion_rate}%
                      </span>
                    </td>
                    <td className="py-2 text-right text-slate-500">{row.avg_dwell} min</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      </> }
    </div>
  );
}
