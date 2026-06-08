type ImpactLevel = "high" | "medium" | "low";
type DefaultDecision = "approve" | "reject" | "require_review";

export interface CleaningStepData {
  step_id: string;
  sequence_order: number;
  issue: {
    description: string;
    affected_rows_percent: number;
    column_name?: string | null;
  };
  recommendation: {
    recommended_action: string;
    rationale: string;
    impact_level: ImpactLevel;
    requires_human_approval: boolean;
    default_decision: DefaultDecision;
  };
}

const IMPACT_STYLES: Record<ImpactLevel, string> = {
  high: "border-l-4 border-red-500 bg-red-50",
  medium: "border-l-4 border-yellow-400 bg-yellow-50",
  low: "border-l-4 border-green-400 bg-white",
};

const IMPACT_BADGE: Record<ImpactLevel, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
};

const DECISION_BADGE: Record<DefaultDecision, string> = {
  approve: "bg-green-100 text-green-700",
  reject: "bg-red-100 text-red-700",
  require_review: "bg-orange-100 text-orange-700",
};

const DECISION_LABEL: Record<DefaultDecision, string> = {
  approve: "Auto-approve",
  reject: "Auto-reject",
  require_review: "Requires review",
};

function Badge({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${className}`}>{children}</span>
  );
}

export function CleaningPlanPreview({ steps }: { steps: CleaningStepData[] }) {
  if (steps.length === 0) {
    return (
      <p className="text-sm text-gray-500 italic">No cleaning steps — dataset has no detected issues.</p>
    );
  }

  return (
    <div className="space-y-3">
      {steps.map((step) => {
        const rec = step.recommendation;
        const impact = rec.impact_level;
        return (
          <div
            key={step.step_id}
            className={`rounded-lg p-4 ${IMPACT_STYLES[impact]}`}
          >
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono text-gray-400">
                  {String(step.sequence_order).padStart(2, "0")}
                </span>
                <Badge className={IMPACT_BADGE[impact]}>{impact} impact</Badge>
                <Badge className={DECISION_BADGE[rec.default_decision]}>
                  {DECISION_LABEL[rec.default_decision]}
                </Badge>
                {rec.requires_human_approval && (
                  <Badge className="bg-purple-100 text-purple-700">Approval required</Badge>
                )}
              </div>
              <span className="text-xs text-gray-500 whitespace-nowrap">
                {step.issue.affected_rows_percent.toFixed(1)}% rows affected
              </span>
            </div>

            <p className="text-sm font-medium text-gray-800 mb-1">{step.issue.description}</p>
            <p className="text-sm text-gray-700 mb-1">
              <span className="font-medium">Action: </span>{rec.recommended_action}
            </p>
            <p className="text-xs text-gray-500">{rec.rationale}</p>
          </div>
        );
      })}
    </div>
  );
}
