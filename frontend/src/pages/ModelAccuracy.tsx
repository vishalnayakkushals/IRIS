import { useEffect, useState } from "react";
import { reportsModelAccuracy } from "../api/client";
import { Card, Title, Text, Badge } from "@tremor/react";

function statusColor(s: string) {
  if (s === "active") return "emerald";
  if (s === "retired") return "slate";
  if (s === "testing") return "amber";
  return "blue";
}

export default function ModelAccuracy() {
  const [versions, setVersions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    reportsModelAccuracy()
      .then((r) => setVersions(r.data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <Title>Model Accuracy</Title>
        <Text>Registered model versions and their evaluation metrics.</Text>
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading…</div>
      ) : versions.length === 0 ? (
        <div className="text-center py-16 text-gray-400 text-sm">No model versions registered.</div>
      ) : (
        <div className="space-y-4">
          {versions.map((v) => (
            <Card key={v.model_id} className="p-5">
              <div className="flex items-start justify-between flex-wrap gap-3">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-slate-700">{v.model_name}</span>
                    <Badge color="slate">{v.version_tag}</Badge>
                    <Badge color={statusColor(v.status)}>{v.status}</Badge>
                  </div>
                  <p className="text-xs text-slate-400 mt-1 font-mono">{v.model_id}</p>
                  {v.artifact_path && <p className="text-xs text-slate-400 mt-0.5">{v.artifact_path}</p>}
                </div>
                <p className="text-xs text-slate-400">{v.created_at ? new Date(v.created_at).toLocaleDateString("en-IN") : ""}</p>
              </div>

              {v.metrics_json && Object.keys(v.metrics_json).length > 0 && (
                <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                  {Object.entries(v.metrics_json as Record<string, any>).map(([key, val]) => (
                    <div key={key} className="bg-slate-50 rounded-lg p-3">
                      <p className="text-xs text-slate-400 uppercase tracking-wide">{key.replace(/_/g, " ")}</p>
                      <p className="text-lg font-bold text-slate-700 mt-1">
                        {typeof val === "number" && val <= 1 && val >= 0
                          ? (val * 100).toFixed(1) + "%"
                          : typeof val === "number"
                          ? val.toFixed(3)
                          : String(val)}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {v.rollback_target_model_id && (
                <p className="mt-3 text-xs text-slate-400">Rollback target: <span className="font-mono">{v.rollback_target_model_id}</span></p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
