"use client";

import { useState } from "react";

export interface MetricSuggestion {
  id: string;
  displayName: string;
  formulaDisplay: string;
  whyItHelps: string;
  requiredColumns: string[];
  needsReview: boolean;
}

type Decision = "approve" | "skip";

interface ApplyResult {
  metricsAdded: string[];
  metricsSkipped: number;
}

function Badge({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${className}`}>
      {children}
    </span>
  );
}

function MetricCard({
  metric,
  decision,
  onDecide,
}: {
  metric: MetricSuggestion;
  decision: Decision | null;
  onDecide: (d: Decision) => void;
}) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start gap-3 flex-wrap mb-3">
        {metric.needsReview ? (
          <Badge className="bg-orange-100 text-orange-700">Needs your review</Badge>
        ) : (
          <Badge className="bg-green-100 text-green-700">Safe to add automatically</Badge>
        )}
        {decision === "approve" && (
          <Badge className="bg-green-100 text-green-800">Approved</Badge>
        )}
        {decision === "skip" && (
          <Badge className="bg-gray-100 text-gray-600">Skipped</Badge>
        )}
      </div>

      <p className="text-sm font-semibold text-gray-800 mb-1">{metric.displayName}</p>
      <p className="text-sm text-gray-500 font-mono mb-2">{metric.formulaDisplay}</p>

      <div className="flex flex-wrap gap-1 mb-3">
        {metric.requiredColumns.map((col) => (
          <span
            key={col}
            className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded"
          >
            {col}
          </span>
        ))}
      </div>

      <button
        onClick={() => setShowDetails((v) => !v)}
        className="text-xs text-gray-400 hover:text-gray-600 underline mb-3"
      >
        {showDetails ? "Hide details" : "Why does this help?"}
      </button>

      {showDetails && (
        <p className="text-xs text-gray-500 bg-gray-50 rounded p-2 mb-3">
          {metric.whyItHelps}
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
          {decision === "skip" ? "Skipped" : "Skip"}
        </button>
      </div>
    </div>
  );
}

function SuccessScreen({ result }: { result: ApplyResult }) {
  return (
    <div className="text-center py-12">
      <div className="text-5xl mb-4">✅</div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Metrics added!</h2>
      <p className="text-gray-500 mb-8 text-sm">
        Your selected metrics were calculated and saved.
      </p>

      <div className="flex gap-4 justify-center mb-8">
        <div className="bg-white border border-gray-200 rounded-xl px-6 py-4 text-center min-w-[120px]">
          <div className="text-2xl font-bold text-green-600">{result.metricsAdded.length}</div>
          <div className="text-xs text-gray-500 mt-1">Metrics added</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl px-6 py-4 text-center min-w-[120px]">
          <div className="text-2xl font-bold text-gray-400">{result.metricsSkipped}</div>
          <div className="text-xs text-gray-500 mt-1">Skipped</div>
        </div>
      </div>

      {result.metricsAdded.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4 text-left max-w-sm mx-auto mb-4">
          <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Added metrics</p>
          <ul className="space-y-1">
            {result.metricsAdded.map((name) => (
              <li key={name} className="text-sm text-gray-700 flex items-center gap-2">
                <span className="text-green-500">+</span> {name}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 text-left max-w-md mx-auto mb-6">
        <p className="text-sm font-semibold text-blue-900 mb-1">
          📁 A new enriched copy was created
        </p>
        <p className="text-sm text-blue-700">
          Your previous data was not overwritten. The enriched version is saved
          separately — you can always go back to the original.
        </p>
      </div>

      <a href="/" className="inline-block text-sm text-gray-500 hover:text-gray-700 underline">
        ← Back to home
      </a>
    </div>
  );
}

export function MetricsReviewFlow({ metrics }: { metrics: MetricSuggestion[] }) {
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState<ApplyResult | null>(null);

  const reviewRequired = metrics.filter((m) => m.needsReview);
  const undecided = reviewRequired.filter((m) => !decisions[m.id]);
  const canApply = undecided.length === 0;

  const approvedMetrics = metrics.filter((m) => {
    if (decisions[m.id]) return decisions[m.id] === "approve";
    return !m.needsReview;
  });

  function decide(id: string, d: Decision) {
    setDecisions((prev) => ({ ...prev, [id]: d }));
  }

  async function applyMetrics() {
    setApplying(true);
    // Simulates POST /feature-plans/{id}/execute
    await new Promise((r) => setTimeout(r, 1200));
    const skipped = metrics.length - approvedMetrics.length;
    setResult({
      metricsAdded: approvedMetrics.map((m) => m.displayName),
      metricsSkipped: skipped,
    });
    setApplying(false);
  }

  if (result) {
    return <SuccessScreen result={result} />;
  }

  return (
    <div>
      {/* Summary bar */}
      <div className="flex gap-4 mb-6 text-sm">
        <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex-1 text-center">
          <div className="text-xl font-bold text-gray-900">{metrics.length}</div>
          <div className="text-gray-500 text-xs">Suggested metrics</div>
        </div>
        <div className="bg-white border border-orange-200 rounded-lg px-4 py-3 flex-1 text-center">
          <div className="text-xl font-bold text-orange-600">{reviewRequired.length}</div>
          <div className="text-gray-500 text-xs">Need your review</div>
        </div>
        <div className="bg-white border border-green-200 rounded-lg px-4 py-3 flex-1 text-center">
          <div className="text-xl font-bold text-green-600">{approvedMetrics.length}</div>
          <div className="text-gray-500 text-xs">Approved so far</div>
        </div>
      </div>

      {/* Metric cards */}
      <div className="space-y-4 mb-8">
        {metrics.map((m) => (
          <MetricCard
            key={m.id}
            metric={m}
            decision={decisions[m.id] ?? null}
            onDecide={(d) => decide(m.id, d)}
          />
        ))}
      </div>

      {/* Action area */}
      {undecided.length > 0 && (
        <p className="text-sm text-orange-600 mb-3 text-center">
          {undecided.length} metric{undecided.length > 1 ? "s" : ""} still need
          {undecided.length === 1 ? "s" : ""} a decision before you can apply.
        </p>
      )}

      <button
        onClick={applyMetrics}
        disabled={!canApply || applying}
        className={`w-full py-3 rounded-xl text-sm font-semibold transition-colors ${
          canApply && !applying
            ? "bg-green-600 hover:bg-green-700 text-white"
            : "bg-gray-200 text-gray-400 cursor-not-allowed"
        }`}
      >
        {applying
          ? "Adding your metrics…"
          : `Apply selected metrics (${approvedMetrics.length} approved)`}
      </button>

      <p className="mt-3 text-xs text-gray-400 text-center">
        Your previous data will not be changed. A new enriched copy will be created.
      </p>
    </div>
  );
}
