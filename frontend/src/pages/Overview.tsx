import { useEffect, useState } from "react";
import { Title, Text, Metric, Card, Grid, BarChart, Select, SelectItem } from "@tremor/react";
import { fetchOverview, fetchTraffic, listStores, StoreOption, TrafficPoint } from "../api/client";

export default function Overview() {
  const [data, setData] = useState({
    total_walkins: 0,
    total_customers: 0,
    total_staff: 0,
    conversion_rate: "0%",
  });
  const [stores, setStores] = useState<StoreOption[]>([]);
  const [storeFilter, setStoreFilter] = useState("");
  const [series, setSeries] = useState<TrafficPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(true);

  useEffect(() => {
    fetchOverview()
      .then((res) => { if (res?.data) setData(res.data); })
      .catch(() => {})
      .finally(() => setLoading(false));

    listStores()
      .then((res) => setStores(res.data?.stores ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setChartLoading(true);
    fetchTraffic(storeFilter || undefined, 30)
      .then((res) => setSeries(res.data?.series ?? []))
      .catch(() => {})
      .finally(() => setChartLoading(false));
  }, [storeFilter]);

  const chartData = series.map((p) => ({
    date: p.date,
    Customers: p.customers,
    Staff: p.staff,
    Conversions: p.conversions,
  }));

  return (
    <div className="space-y-6 animate-in fade-in zoom-in duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <Title>Business Overview</Title>
          <Text>Real-time walk-in and conversion metrics from the YOLO/GPT pipeline.</Text>
        </div>
        {stores.length > 0 && (
          <Select
            placeholder="All Stores"
            value={storeFilter}
            onValueChange={(v) => setStoreFilter(v === "all" ? "" : v)}
            className="w-48"
          >
            <SelectItem value="all">All Stores</SelectItem>
            {stores.map((s) => (
              <SelectItem key={s.store_id} value={s.store_id}>{s.store_id}</SelectItem>
            ))}
          </Select>
        )}
      </div>

      <Grid numItemsSm={2} numItemsLg={4} className="gap-6">
        <Card decoration="top" decorationColor="blue">
          <Text>Total Walk-ins</Text>
          <Metric>{loading ? "—" : data.total_walkins.toLocaleString()}</Metric>
        </Card>
        <Card decoration="top" decorationColor="emerald">
          <Text>Total Customers</Text>
          <Metric>{loading ? "—" : data.total_customers.toLocaleString()}</Metric>
        </Card>
        <Card decoration="top" decorationColor="amber">
          <Text>Staff Count</Text>
          <Metric>{loading ? "—" : data.total_staff.toLocaleString()}</Metric>
        </Card>
        <Card decoration="top" decorationColor="indigo">
          <Text>Conversion Rate</Text>
          <Metric>{loading ? "—" : data.conversion_rate}</Metric>
        </Card>
      </Grid>

      <Card>
        <div className="flex items-center justify-between mb-2">
          <Title>Traffic Flow — Last 30 Days</Title>
          {chartLoading && <Text className="text-xs text-slate-400">Loading…</Text>}
        </div>
        {!chartLoading && chartData.length === 0 ? (
          <div className="h-56 flex items-center justify-center text-slate-400 bg-slate-50/50 rounded-lg border border-dashed text-sm">
            No traffic data yet. Run the pipeline to populate this chart.
          </div>
        ) : (
          <BarChart
            className="mt-4 h-56"
            data={chartData}
            index="date"
            categories={["Customers", "Staff", "Conversions"]}
            colors={["blue", "amber", "emerald"]}
            stack={false}
            showLegend
            showAnimation
            yAxisWidth={40}
          />
        )}
      </Card>
    </div>
  );
}
