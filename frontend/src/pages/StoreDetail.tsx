import { useEffect, useState } from "react";
import { Title, Text, Metric, Card, Grid, TextInput, Button } from "@tremor/react";
import { Search } from "lucide-react";
import { api } from "../api/client";

export default function StoreDetail() {
  const [storeId, setStoreId] = useState("TEST_STORE_D07");
  const [query, setQuery] = useState("TEST_STORE_D07");
  const [data, setData] = useState({
    footfall: 0,
    bounce_rate: "0%",
    dwell_time: "0 min",
    status: ""
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStore() {
      setLoading(true);
      try {
        const res = await api.get(`/detail/${storeId}/metrics`);
        if (res && res.data) {
          setData(res.data);
        }
      } catch (err) {
        console.error("Failed to fetch store details", err);
      } finally {
        setLoading(false);
      }
    }
    fetchStore();
  }, [storeId]);

  return (
    <div className="space-y-6 animate-in fade-in zoom-in duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <Title>Store Detail View</Title>
          <Text>Drill down into specific store performance and analytics.</Text>
        </div>
        <div className="flex gap-2">
            <TextInput 
                placeholder="Enter Store ID" 
                value={query} 
                onChange={(e) => setQuery(e.target.value)} 
            />
            <Button icon={Search} onClick={() => setStoreId(query)}>Search</Button>
        </div>
      </div>

      <Grid numItemsSm={1} numItemsLg={3} className="gap-6">
        <Card decoration="top" decorationColor="indigo">
          <Text>Daily Footfall</Text>
          <Metric>{loading ? "-" : data.footfall}</Metric>
        </Card>
        <Card decoration="top" decorationColor="rose">
          <Text>Bounce Rate</Text>
          <Metric>{loading ? "-" : data.bounce_rate}</Metric>
        </Card>
        <Card decoration="top" decorationColor="amber">
          <Text>Average Dwell Time</Text>
          <Metric>{loading ? "-" : data.dwell_time}</Metric>
        </Card>
      </Grid>
      
      <Card className="mt-6">
         <Title>Recent Store Activity</Title>
         <Text className="mt-2 text-slate-500 text-sm">
             {data.status || "Activity logs will appear here based on the selected store ID."}
         </Text>
      </Card>
    </div>
  );
}
