import { useEffect, useState } from "react";
import { Title, Text, Metric, Card, Grid } from "@tremor/react";
import { fetchOverview } from "../api/client";

export default function Overview() {
  const [data, setData] = useState({
    total_walkins: 0,
    total_customers: 0,
    total_staff: 0,
    conversion_rate: "0%"
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const res = await fetchOverview();
        if (res && res.data) {
          setData(res.data);
        }
      } catch (err) {
        console.error("Failed to fetch overview data", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  return (
    <div className="space-y-6 animate-in fade-in zoom-in duration-500">
      <div>
        <Title>Business Overview</Title>
        <Text>Real-time walk-in and conversion metrics processing directly from the YOLO/GPT event pipeline.</Text>
      </div>

      <Grid numItemsSm={2} numItemsLg={4} className="gap-6">
        <Card decoration="top" decorationColor="blue">
          <Text>Total Walk-ins</Text>
          <Metric>{loading ? "-" : data.total_walkins}</Metric>
        </Card>
        <Card decoration="top" decorationColor="emerald">
          <Text>Total Customers</Text>
          <Metric>{loading ? "-" : data.total_customers}</Metric>
        </Card>
        <Card decoration="top" decorationColor="amber">
          <Text>Staff Count</Text>
          <Metric>{loading ? "-" : data.total_staff}</Metric>
        </Card>
        <Card decoration="top" decorationColor="indigo">
          <Text>Conversion Rate</Text>
          <Metric>{loading ? "-" : data.conversion_rate}</Metric>
        </Card>
      </Grid>
      
      <Card className="mt-6">
         <Title>Traffic Flow Over Time</Title>
         <div className="h-72 flex items-center justify-center text-slate-400 bg-slate-50/50 rounded-lg mt-4 border border-dashed">
            (Tremor Chart implementation pending time-series API)
         </div>
      </Card>
    </div>
  );
}
