import { useEffect, useState } from "react";
import {
  qaAccuracy, qaRetrain, qaImprovePrompt, qaApplyImprovement,
  qaGetImprovements, reportsModelAccuracy,
} from "../api/client";
import { Card, Title, Text, Badge } from "@tremor/react";
import { Zap, Wand2, CheckCircle, Clock, ChevronDown, ChevronUp } from "lucide-react";
import { useStore } from "../context/StoreContext";

export default function ModelFeedback() {
  const { storeId } = useStore();
  const [accuracy, setAccuracy] = useState<any>(null);
  const [modelVersions, setModelVersions] = useState<any[]>([]);
  const [retraining, setRetraining] = useState(false);

  // Option B — prompt improvement
  const [improving, setImproving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [suggestion, setSuggestion] = useState<{ text: string; based_on_count: number } | null>(null);
  const [improvements, setImprovements] = useState<any[]>([]);
  const [activeText, setActiveText] = useState("");
  const [showActivePrompt, setShowActivePrompt] = useState(false);

  const [toast, setToast] = useState("");

  function flash(msg: string) { setToast(msg); setTimeout(() => setToast(""), 5000); }

  function loadImprovements() {
    if (!storeId) return;
    qaGetImprovements(storeId).then((r) => {
      setImprovements(r.data.improvements || []);
      setActiveText(r.data.active_text || "");
    }).catch(() => {});
  }

  useEffect(() => {
    const ctrl = new AbortController();
    reportsModelAccuracy({ signal: ctrl.signal }).then((r) => setModelVersions(r.data)).catch(() => {});
    return () => ctrl.abort();
  }, []);

  useEffect(() => {
    if (!storeId) return;
    const ctrl = new AbortController();
    qaAccuracy(storeId, { signal: ctrl.signal }).then((r) => setAccuracy(r.data)).catch(() => {});
    loadImprovements();
    return () => ctrl.abort();
  }, [storeId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRetrain() {
    if (!storeId) return;
    if (!confirm(`Sync confirmed corrections to pipeline for ${storeId}?\n\nThis writes a corrections file that the pipeline loads on next run.`)) return;
    setRetraining(true);
    try {
      const { data } = await qaRetrain(storeId);
      if (data.status === "skipped") {
        flash(data.message || "No confirmed feedback rows — confirm some frames in Frame Review first.");
      } else {
        flash(`Done: ${data.rule_count} corrections synced to pipeline (${data.version_tag}). Next run will apply them.`);
        reportsModelAccuracy().then((r) => setModelVersions(r.data));
      }
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Sync failed");
    } finally { setRetraining(false); }
  }

  async function handleImprovePrompt() {
    if (!storeId) return;
    setImproving(true);
    setSuggestion(null);
    try {
      const { data } = await qaImprovePrompt(storeId);
      setSuggestion({ text: data.suggestion, based_on_count: data.based_on_count });
      flash(`GPT analysed ${data.based_on_count} rejected frames (${data.images_attached} images attached). Review the suggestion below.`);
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Improvement request failed — check OPENAI_API_KEY and that there are rejected frames.");
    } finally { setImproving(false); }
  }

  async function handleApplyImprovement() {
    if (!storeId || !suggestion) return;
    setApplying(true);
    try {
      await qaApplyImprovement(storeId, { suggestion: suggestion.text, based_on_count: suggestion.based_on_count });
      flash("Improvement applied. The next pipeline run will include this rule in the GPT prompt.");
      setSuggestion(null);
      loadImprovements();
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Apply failed");
    } finally { setApplying(false); }
  }

  const storeVersions = modelVersions.filter((v) =>
    v.model_name?.includes(storeId) || !storeId
  );

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-20 right-8 z-50 bg-slate-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg max-w-sm">
          {toast}
        </div>
      )}

      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <Title>Model Feedback & Retrain</Title>
          <Text>Two ways to improve GPT accuracy: sync corrections for re-runs (Option A) or let GPT improve its own prompt (Option B).</Text>
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
            <Text className="text-xs uppercase tracking-wide text-slate-400">Rejected</Text>
            <p className="text-2xl font-bold mt-1 text-rose-600">{accuracy.rejected}</p>
          </Card>
        </div>
      )}

      {/* ── Option A ── */}
      <Card className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="font-semibold text-slate-800 text-sm flex items-center gap-2">
              <CheckCircle size={15} className="text-emerald-500" />
              Option A — Sync Corrections to Pipeline
            </p>
            <p className="text-xs text-slate-500 mt-1 max-w-xl">
              Takes every <strong>confirmed</strong> feedback row and writes a corrections file.
              On the next pipeline run, any session whose image + walk-in ID matches a human correction
              will have its role overridden automatically — without calling GPT again.
              Use this after re-running the pipeline on the same date's footage.
            </p>
          </div>
          <button
            type="button"
            onClick={handleRetrain}
            disabled={retraining || !storeId}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors shrink-0"
          >
            <Zap size={13} className={retraining ? "animate-spin" : ""} />
            {retraining ? "Syncing…" : "Sync Corrections"}
          </button>
        </div>
        <div className="text-xs text-slate-400 bg-slate-50 rounded-lg px-3 py-2">
          How it works: Confirm frames in <strong>QA → Frame Review</strong> or <strong>QA → Walk-in Sessions</strong> →
          click Sync Corrections → run the pipeline again. Corrected roles appear in Walk-in Sessions and analytics.
        </div>
      </Card>

      {/* ── Option B ── */}
      <Card className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="font-semibold text-slate-800 text-sm flex items-center gap-2">
              <Wand2 size={15} className="text-violet-500" />
              Option B — Improve Prompt with AI
            </p>
            <p className="text-xs text-slate-500 mt-1 max-w-xl">
              Takes up to 20 <strong>rejected</strong> frames + their actual images, sends them to GPT with the
              current prompt, and asks GPT to write a short additional rule that would have prevented those errors.
              One extra API call per session (not per image). Applied rules are appended to the GPT prompt
              on every future pipeline run for this store.
            </p>
          </div>
          <button
            type="button"
            onClick={handleImprovePrompt}
            disabled={improving || !storeId}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50 transition-colors shrink-0"
          >
            <Wand2 size={13} className={improving ? "animate-spin" : ""} />
            {improving ? "Asking GPT…" : "Improve Prompt"}
          </button>
        </div>

        {/* GPT suggestion card */}
        {suggestion && (
          <div className="border border-violet-200 bg-violet-50 rounded-xl p-4 space-y-3">
            <p className="text-xs font-semibold text-violet-700 uppercase tracking-wide">
              GPT Suggestion — based on {suggestion.based_on_count} rejected frames
            </p>
            <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap font-mono bg-white border border-violet-100 rounded-lg p-3">
              {suggestion.text}
            </p>
            <p className="text-xs text-slate-500">
              Review this carefully. If it looks correct and specific, click Apply. If it's too generic, reject and try again after adding more feedback.
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleApplyImprovement}
                disabled={applying}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50 transition-colors"
              >
                <CheckCircle size={11} />
                {applying ? "Applying…" : "Apply to Future Runs"}
              </button>
              <button
                type="button"
                onClick={() => setSuggestion(null)}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 text-slate-500 hover:bg-slate-50 transition-colors"
              >
                Discard
              </button>
            </div>
          </div>
        )}

        {/* Active prompt improvements */}
        {activeText && (
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setShowActivePrompt((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 transition-colors"
            >
              {showActivePrompt ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {showActivePrompt ? "Hide" : "Show"} active store-specific rules ({improvements.length} applied)
            </button>
            {showActivePrompt && (
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-2">
                  Appended to GPT prompt on every run for {storeId}
                </p>
                <pre className="text-xs text-slate-700 whitespace-pre-wrap font-mono leading-relaxed">{activeText}</pre>
              </div>
            )}
          </div>
        )}

        {/* Improvement history */}
        {improvements.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Applied Improvements</p>
            {improvements.map((imp) => (
              <div key={imp.id} className="flex items-start gap-3 text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
                <Clock size={11} className="mt-0.5 shrink-0 text-slate-400" />
                <div className="min-w-0">
                  <p className="font-mono text-[10px] text-slate-400">{imp.id} · {imp.based_on_count} frames · {imp.actor}</p>
                  <p className="text-slate-600 truncate mt-0.5">{imp.text?.slice(0, 120)}{imp.text?.length > 120 ? "…" : ""}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="text-xs text-slate-400 bg-slate-50 rounded-lg px-3 py-2">
          Cost: one GPT call per click (with up to 8 images). Improvement is store-specific — it only affects {storeId || "the selected store"}'s runs.
        </div>
      </Card>

      {/* Rule file history (Option A artifacts) */}
      <div>
        <Title>Corrections Sync History</Title>
        <Text className="mb-4">Each sync creates a versioned corrections file for {storeId || "all stores"}.</Text>
        {storeVersions.length === 0 ? (
          <div className="text-center py-10 text-gray-400 text-sm border rounded-lg">
            No syncs yet. Confirm some frames and click Sync Corrections.
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
                    <span>{v.metrics_json.rule_count} corrections</span>
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
