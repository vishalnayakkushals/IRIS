import { useEffect, useState } from "react";
import { adminListStores, qaAccuracy, qaRetrain, reportsModelAccuracy } from "../api/client";
import { Card, Title, Text, Badge, Button } from "@tremor/react";
import { Zap } from "lucide-react";
import StoreSelect from "../components/StoreSelect";

export default function ModelFeedback() {
  const [stores, setStores] = useState<any[]>([]);
  const [storeId, setStoreId] = useState("");
  const [accuracy, setAccuracy] = useState<any>(null);
  const [modelVersions, setModelVersions] = useState<any[]>([]);
  const [retraining, setRetraining] = useState(false);
  const [toast, setToast] = useState("");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 4000); }

  useEffect(() => {
    adminListStores().then((r) => {
      setStores(r.data);
      if (r.data.length) setStoreId(r.data[0].store_id);
    });
    reportsModelAccuracy().then((r) => setModelVersions(r.data));
  }, []);

  useEffect(() => {
    if (!storeId) return;
    qaAccuracy(storeId).then((r) => setAccuracy(r.data)).catch(() => {});
  }, [storeId]);

  async function handleRetrain() {
    if (!storeId) return;
    if (!confirm(`Generate rule file from all confirmed feedback for ${storeId}?`)) return;
    setRetraining(true);
    try {
      const { data } = await qaRetrain(storeId);
      if (data.status === "skipped") {
        flash(data.message || "No confirmed feedback rows — confirm some frames in Frame Review first.");
      } else {
        flash(`Retrain complete: ${data.rule_count} rules written as ${data.version_tag}`);
        reportsModelAccuracy().then((r) => setModelVersions(r.data));
      }
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Retrain failed");
    } finally { setRetraining(false); }
  }

  const storeVersions = modelVersions.filter((v) =>
    v.model_name?.includes(storeId) || !storeId
  );

  return (
    <div className="space-y-6">
      {toast && <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">{toast}</div>}

      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Title>Model Feedback & Retrain</Title>
          <Text>Generate rule files from confirmed QA feedback to improve label accuracy.</Text>
        </div>
        <div className="flex gap-2 items-center">
          <div className="w-72">
            <StoreSelect stores={stores} value={storeId} onChange={setStoreId} placeholder="Select store" />
          </div>
          <Button icon={Zap} loading={retraining} onClick={handleRetrain} color="violet">
            Generate Rule File
          </Button>
        </div>
      </div>

      {/* Accuracy summary */}
      {accuracy && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4">
            <Text className="text-xs uppercase tracking-wide text-slate-400">Accuracy</Text>
            <p className="text-2xl font-bold mt-1">{accuracy.accuracy_pct}%</p>
            <p className="text-xs text-slate-400 mt-0.5">{accuracy.scored_rows} scored rows</p>
          </Card>
          <Card className="p-4">
            <Text className="text-xs uppercase tracking-wide text-slate-400">Total Feedback</Text>
            <p className="text-2xl font-bold mt-1">{accuracy.total}</p>
          </Card>
          <Card className="p-4">
            <Text className="text-xs uppercase tracking-wide text-slate-400">Confirmed</Text>
            <p className="text-2xl font-bold mt-1 text-emerald-600">{accuracy.confirmed}</p>
          </Card>
          <Card className="p-4">
            <Text className="text-xs uppercase tracking-wide text-slate-400">Pending</Text>
            <p className="text-2xl font-bold mt-1 text-amber-600">{accuracy.pending}</p>
          </Card>
        </div>
      )}

      {/* Workflow guide */}
      <Card className="p-5 bg-slate-50">
        <p className="font-semibold text-slate-700 mb-3 text-sm">How retraining works</p>
        <ol className="space-y-2 text-sm text-slate-600 list-decimal list-inside">
          <li>Run the on-fly pipeline to generate image scan results (Scheduler → Sync Now)</li>
          <li>Review individual frames in <strong>Frame Review</strong> — approve or reject predicted labels</li>
          <li>Once you have confirmed rows, click <strong>Generate Rule File</strong> here</li>
          <li>A JSON rule file is written to <code className="bg-slate-200 px-1 rounded text-xs">data/models/</code> and registered as a model version</li>
          <li>The YOLO/GPT pipeline loads the latest rule file automatically on next run</li>
        </ol>
      </Card>

      {/* Model version history */}
      <div>
        <Title>Rule File History</Title>
        <Text className="mb-4">Rule files generated from confirmed feedback for {storeId || "all stores"}.</Text>
        {storeVersions.length === 0 ? (
          <div className="text-center py-10 text-gray-400 text-sm border rounded-lg">
            No rule files yet. Confirm some frames and click Generate Rule File.
          </div>
        ) : (
          <div className="space-y-3">
            {storeVersions.map((v) => (
              <Card key={v.model_id} className="p-4 flex items-center justify-between flex-wrap gap-3">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-slate-700 text-sm">{v.model_name}</span>
                    <Badge color="slate">{v.version_tag}</Badge>
                    <Badge color={v.status === "active" ? "emerald" : "slate"}>{v.status}</Badge>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5 font-mono">{v.artifact_path}</p>
                </div>
                <div className="flex items-center gap-4 text-sm text-slate-500">
                  {v.metrics_json?.rule_count != null && (
                    <span>{v.metrics_json.rule_count} rules</span>
                  )}
                  <span>{v.created_at ? new Date(v.created_at).toLocaleDateString("en-IN") : ""}</span>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
