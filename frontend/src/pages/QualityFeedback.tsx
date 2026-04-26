import { Title, Text, Card } from "@tremor/react";

export default function QualityFeedback() {
  return (
    <div className="space-y-6 animate-in fade-in zoom-in duration-500">
      <div>
        <Title>Quality Assurance & Feedback</Title>
        <Text>Review specific frame detections for model retraining, matching the legacy Streamlit workflow.</Text>
      </div>

      <Card className="mt-6 border border-dashed rounded-lg shadow-sm text-center py-16 text-slate-500">
          <Text className="text-sm font-semibold">QA API endpoints pending backend configuration.</Text>
          <Text className="text-xs">
              When data returns, this pane will contain frame visualizations 
              to flag false positives directly into Postgres.
          </Text>
      </Card>
      
      <div className="flex gap-4">
          <Card className="flex-1 border-l-4 border-l-blue-500">
              <Text className="font-semibold text-slate-700">Total Frames Reviewed</Text>
              <Title>0</Title>
          </Card>
          <Card className="flex-1 border-l-4 border-l-emerald-500">
              <Text className="font-semibold text-slate-700">Valid Detections</Text>
              <Title>0</Title>
          </Card>
          <Card className="flex-1 border-l-4 border-l-rose-500">
              <Text className="font-semibold text-slate-700">Flagged Exceptions</Text>
              <Title>0</Title>
          </Card>
      </div>
    </div>
  );
}
