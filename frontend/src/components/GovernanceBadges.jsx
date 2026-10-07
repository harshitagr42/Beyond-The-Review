import { ShieldCheck, Activity, Target } from "lucide-react";

export default function GovernanceBadges({ summary }) {
  if (!summary) return null;

  return (
    <div className="governance-row" id="governance-badges">
      <div className="governance-badge positive">
        <div className="badge-dot" />
        <ShieldCheck size={14} />
        <span>PII Redacted: {summary.pii_redacted_count.toLocaleString()} items</span>
      </div>
      <div className="governance-badge info">
        <div className="badge-dot" />
        <Target size={14} />
        <span>Validation Accuracy: {summary.model_validation_accuracy}</span>
      </div>
      <div className="governance-badge positive">
        <div className="badge-dot" />
        <Activity size={14} />
        <span>Model Drift: {summary.drift_status}</span>
      </div>
    </div>
  );
}
