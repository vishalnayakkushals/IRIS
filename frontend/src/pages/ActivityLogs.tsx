import { useEffect, useState } from "react";
import { adminListActivity } from "../api/client";
import { Card, Title, Text, Badge } from "@tremor/react";
import { RefreshCw } from "lucide-react";

const ACTION_COLORS: Record<string, string> = {
  "store.create": "emerald",
  "store.update": "blue",
  "store.delete": "rose",
  "user.create": "emerald",
  "user.update": "blue",
  "user.delete": "rose",
  "user.password_reset": "amber",
  "role.create": "emerald",
  "role.delete": "rose",
  "role.permissions_set": "blue",
  "settings.update": "violet",
  "employee.create": "emerald",
  "employee.delete": "rose",
  "camera.upsert": "blue",
  "camera.delete": "rose",
  "location.upsert": "blue",
  "location.delete": "rose",
  "store_access.replace": "violet",
  "store_master.upsert": "blue",
};

function actionColor(code: string): string {
  return ACTION_COLORS[code] || "slate";
}

export default function ActivityLogs() {
  const [logs, setLogs] = useState<any[]>([]);
  const [actor, setActor] = useState("");
  const [limit, setLimit] = useState(100);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    adminListActivity(actor || undefined, limit)
      .then((r) => setLogs(r.data))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Title>Activity Logs</Title>
          <Text>Audit trail of all admin actions performed in IRIS.</Text>
        </div>
        <div className="flex gap-2 items-center">
          <input
            placeholder="Filter by email"
            className="border rounded px-3 py-2 text-sm w-52 focus:outline-none focus:ring-2 focus:ring-blue-300"
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
          <select
            className="border rounded px-3 py-2 text-sm"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          >
            <option value={50}>Last 50</option>
            <option value={100}>Last 100</option>
            <option value={250}>Last 250</option>
            <option value={500}>Last 500</option>
          </select>
          <button
            onClick={load}
            disabled={loading}
            className="p-2 rounded border text-slate-500 hover:text-blue-600 hover:border-blue-400 disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <Card className="p-0 overflow-hidden">
        {loading ? (
          <div className="text-center py-12 text-gray-400 text-sm">Loading…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left whitespace-nowrap">
              <thead>
                <tr className="bg-slate-50 border-b text-slate-500 text-xs uppercase tracking-wider font-semibold">
                  <th className="px-5 py-3">Time</th>
                  <th className="px-5 py-3">Actor</th>
                  <th className="px-5 py-3">Action</th>
                  <th className="px-5 py-3">Store</th>
                  <th className="px-5 py-3">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((l) => (
                  <tr key={l.id} className="hover:bg-slate-50/50">
                    <td className="px-5 py-3 text-slate-400 text-xs">
                      {l.created_at ? new Date(l.created_at).toLocaleString("en-IN", { hour12: true }) : "—"}
                    </td>
                    <td className="px-5 py-3 text-slate-600">{l.actor_email}</td>
                    <td className="px-5 py-3">
                      <Badge color={actionColor(l.action_code) as any}>{l.action_code}</Badge>
                    </td>
                    <td className="px-5 py-3 text-slate-500">{l.store_id || "—"}</td>
                    <td className="px-5 py-3 text-slate-400 text-xs max-w-xs truncate">
                      {l.payload_json ? JSON.stringify(l.payload_json) : "—"}
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr><td colSpan={5} className="text-center py-12 text-gray-400 text-sm">No activity records.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
