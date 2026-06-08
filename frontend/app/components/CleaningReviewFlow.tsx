"use client";

import { useState } from "react";

export type RiskLevel = "high" | "medium" | "low";

export interface SuggestedFix {
  id: string;
  whatWasFound: string;
  whyItMatters: string;
  suggestedAction: string;
  riskLevel: RiskLevel;
  needsReview: boolean;
  affectedPercent: number;
}

type Decision = "approve" | "skip";

interface ApplyResult {
  fixesApplied: number;
  fixesSkipped: number;
  rowsChanged: number;
}

const RISK_COLORS: Record<RiskLevel, string> = {
  high: "border-l-4 border-red-400 bg-red-50",
  medium: "border-l-4 border-yellow-400 bg-yellow-50",
  low: "border-l-4 border-green-400 bg-white",
};

const RISK_LABEL: Record<RiskLevel, string> = {
  high: "High impact",
  medium: "Medium impact",
  low: "Low impact",
};

const RISK_BADGE: Record<RiskLevel, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
};

function Badge({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${className}`}>
      {children}
    </span>
  );
}

function FixCard({
  fix,
  decision,
  onDecide,
}: {
  fix: SuggestedFix;
  decision: Decision | null;
  onDecide: (d: Decision) => void;
}) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className={`rounded-lg p-5 ${RISK_COLORS[fix.riskLevel]}`}>
      <div className="flex items-start gap-3 flex-wrap mb-3">
        <Badge className={RISK_BADGE[fix.riskLevel]}>{RISK_LABEL[fix.riskLevel]}</Badge>
        {fix.needsReview ? (
          <Badge className="bg-orange-100 text-orange-700">Needs your review</Badge>
        ) : (
          <Badge className="bg-green-100 text-green-700">Safe to apply automatically</Badge>
        )}
        <span className="ml-auto text-xs text-gray-500">
          {fix.affectedPercent.toFixed(1)}% of rows affected
        </span>
      </div>

      <p className="text-sm font-semibold text-gray-800 mb-1">{fix.whatWasFound}</p>
      <p className="text-sm text-gray-700 mb-1">
        <span className="font-medium">What will change: </span>
        {fix.suggestedAction}
      </p>

      <button
        onClick={() => setShowDetails((v) => !v)}
        className="text-xs text-gray-400 hover:text-gray-600 underline mb-3"
      >
        {showDetails ? "Hide details" : "Show details"}
      </button>

      {showDetails && (
        <p className="text-xs text-gray-500 bg-white/60 rounded p-2 mb-3">
          {fix.whyItMatters}
        </p>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => onDecide("approve")}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            decision === "approve"
              ? "bg-green-600 text-white"
              : "bg-white border border-gray-300 text-gray-700 hover:border-green-500 hover:text-green-700"
          }`}
        >
          {decision === "approve" ? "✓ Approved" : "Approve"}
        </button>
        <button
          onClick={() => onDecide("skip")}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            decision === "skip"
              ? "bg-gray-500 text-white"
              : "bg-white border border-gray-300 text-gray-600 hover:border-gray-500"
          }`}
        >
          {decision === "skip" ? "Skipped" : "Skip this fix"}
        </button>
      </div>
    </div>
  );
}

function ResultScreen({ result, total }: { result: ApplyResult; total: number }) {
  return (
    <div className="text-center py-12">
      <div className="text-5xl mb-4">✅</div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Your fixes were applied!</h2>
      <p className="text-gray-500 mb-8 text-sm">
        Your data has been cleaned based on the fixes you approved.
      </p>

      <div className="flex gap-4 justify-center mb-8">
        <div className="bg-white border border-gray-200 rounded-xl px-6 py-4 text-center min-w-[120px]">
          <div className="text-2xl font-bold text-green-600">{result.fixesApplied}</div>
          <div className="text-xs text-gray-500 mt-1">Fixes applied</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl px-6 py-4 text-center min-w-[120px]">
          <div className="text-2xl font-bold text-gray-400">{result.fixesSkipped}</div>
          <div className="text-xs text-gray-500 mt-1">Skipped</div>
        </div>
        {result.rowsChanged > 0 && (
          <div className="bg-white border border-gray-200 rounded-xl px-6 py-4 text-center min-w-[120px]">
            <div className="text-2xl font-bold text-blue-600">{result.rowsChanged}</div>
            <div className="text-xs text-gray-500 mt-1">Rows updated</div>
          </div>
        )}
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 text-left max-w-md mx-auto mb-6">
        <p className="text-sm font-semibold text-blue-900 mb-1">📁 A new clean copy was created</p>
        <p className="text-sm text-blue-700">
          Your original file is unchanged. The cleaned version is saved separately — you can always
          go back to the original.
        </p>
      </div>

      <a
        href="/"
        className="inline-block text-sm text-gray-500 hover:text-gray-700 underline"
      >
        ← Back to home
      </a>
    </div>
  );
}

export function CleaningReviewFlow({ fixes }: { fixes: SuggestedFix[] }) {
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState<ApplyResult | null>(null);

  const reviewRequired = fixes.filter((f) => f.needsReview);
  const undecidedReview = reviewRequired.filter((f) => !decisions[f.id]);
  const canApply = undecidedReview.length === 0;

  const approvedCount = fixes.filter((f) => {
    if (decisions[f.id]) return decisions[f.id] === "approve";
    return !f.needsReview; // auto-approved if safe and no explicit decision
  }).length;

  function decide(id: string, d: Decision) {
    setDecisions((prev) => ({ ...prev, [id]: d }));
  }

  async function applyFixes() {
    setApplying(true);
    // Simulate API call — in production this calls POST /cleaning-plans/{id}/execute
    await new Promise((r) => setTimeout(r, 1200));

    const approved = fixes.filter((f) => {
      if (decisions[f.id]) return decisions[f.id] === "approve";
      return !f.needsReview;
    });
    const skipped = fixes.length - approved.length;
    const rowsChanged = approved.reduce((sum, f) => sum + Math.round(f.affectedPercent), 0);

    setResult({ fixesApplied: approved.length, fixesSkipped: skipped, rowsChanged });
    setApplying(false);
  }

  if (result) {
    return <ResultScreen result={result} total={fixes.length} />;
  }

  return (
    <div>
      {/* Summary bar */}
      <div className="flex gap-4 mb-6 text-sm">
        <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex-1 text-center">
          <div className="text-xl font-bold text-gray-900">{fixes.length}</div>
          <div className="text-gray-500 text-xs">Suggested fixes</div>
        </div>
        <div className="bg-white border border-orange-200 rounded-lg px-4 py-3 flex-1 text-center">
          <div className="text-xl font-bold text-orange-600">{reviewRequired.length}</div>
          <div className="text-gray-500 text-xs">Need your review</div>
        </div>
        <div className="bg-white border border-green-200 rounded-lg px-4 py-3 flex-1 text-center">
          <div className="text-xl font-bold text-green-600">
            {fixes.length - reviewRequired.length}
          </div>
          <div className="text-gray-500 text-xs">Safe to auto-apply</div>
        </div>
      </div>

      {/* Fixes list */}
      <div className="space-y-4 mb-8">
        {fixes.map((fix) => (
          <FixCard
            key={fix.id}
            fix={fix}
            decision={decisions[fix.id] ?? null}
            onDecide={(d) => decide(fix.id, d)}
          />
        ))}
      </div>

      {/* Action area */}
      {undecidedReview.length > 0 && (
        <p className="text-sm text-orange-600 mb-3 text-center">
          {undecidedReview.length} fix{undecidedReview.length > 1 ? "es" : ""} still need
          {undecidedReview.length === 1 ? "s" : ""} your decision before you can apply.
        </p>
      )}

      <button
        onClick={applyFixes}
        disabled={!canApply || applying}
        className={`w-full py-3 rounded-xl text-sm font-semibold transition-colors ${
          canApply && !applying
            ? "bg-green-600 hover:bg-green-700 text-white"
            : "bg-gray-200 text-gray-400 cursor-not-allowed"
        }`}
      >
        {applying ? "Applying your fixes…" : `Apply selected fixes (${approvedCount} approved)`}
      </button>

      <p className="mt-3 text-xs text-gray-400 text-center">
        Your original file will not be changed. A new clean copy will be created.
      </p>
    </div>
  );
}
