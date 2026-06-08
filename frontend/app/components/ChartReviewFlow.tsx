"use client";

import { useState } from "react";

export interface ChartSuggestion {
  id: string;
  title: string;
  chartType: "line" | "bar" | "pie" | "scatter";
  inputTable: string;
  xColumn: string;
  yColumn?: string;
  whyItHelps: string;
  needsReview: boolean;
}

export interface GeneratedChart {
  id: string;
  title: string;
  chartType: string;
  xColumn: string;
  yColumn?: string;
  dataPoints: number;
  description: string;
}

type Decision = "approve" | "skip";

const CHART_TYPE_LABEL: Record<string, string> = {
  line: "Line chart",
  bar: "Bar chart",
  pie: "Pie chart",
  scatter: "Scatter plot",
};

const CHART_TYPE_COLOR: Record<string, string> = {
  line: "bg-blue-100 text-blue-700",
  bar: "bg-purple-100 text-purple-700",
  pie: "bg-pink-100 text-pink-700",
  scatter: "bg-orange-100 text-orange-700",
};

function Badge({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${className}`}>
      {children}
    </span>
  );
}

function ChartCard({
  chart,
  decision,
  onDecide,
}: {
  chart: ChartSuggestion;
  decision: Decision | null;
  onDecide: (d: Decision) => void;
}) {
  const [showWhy, setShowWhy] = useState(false);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start gap-2 flex-wrap mb-3">
        <Badge className={CHART_TYPE_COLOR[chart.chartType] ?? "bg-gray-100 text-gray-600"}>
          {CHART_TYPE_LABEL[chart.chartType] ?? chart.chartType}
        </Badge>
        {chart.needsReview && (
          <Badge className="bg-orange-100 text-orange-700">Needs your review</Badge>
        )}
        {decision === "approve" && (
          <Badge className="bg-green-100 text-green-800">Approved</Badge>
        )}
        {decision === "skip" && (
          <Badge className="bg-gray-100 text-gray-600">Skipped</Badge>
        )}
      </div>

      <p className="text-sm font-semibold text-gray-800 mb-1">{chart.title}</p>

      <div className="flex flex-wrap gap-1 mb-3">
        <span className="text-xs text-gray-400">Data used:</span>
        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
          {chart.inputTable}
        </span>
        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
          {chart.xColumn}
        </span>
        {chart.yColumn && (
          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
            {chart.yColumn}
          </span>
        )}
      </div>

      <button
        onClick={() => setShowWhy((v) => !v)}
        className="text-xs text-gray-400 hover:text-gray-600 underline mb-3"
      >
        {showWhy ? "Hide" : "Why this chart helps"}
      </button>

      {showWhy && (
        <p className="text-xs text-gray-500 bg-gray-50 rounded p-2 mb-3">{chart.whyItHelps}</p>
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

function ChartPreviewCard({ chart }: { chart: GeneratedChart }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <Badge className={CHART_TYPE_COLOR[chart.chartType] ?? "bg-gray-100 text-gray-600"}>
          {CHART_TYPE_LABEL[chart.chartType] ?? chart.chartType}
        </Badge>
        <span className="text-xs text-gray-400">{chart.dataPoints} data points</span>
      </div>

      <p className="text-sm font-semibold text-gray-800 mb-1">{chart.title}</p>
      <p className="text-xs text-gray-500 mb-3">{chart.description}</p>

      {/* Placeholder chart area */}
      <div className="w-full h-32 bg-gray-50 border border-dashed border-gray-200 rounded flex items-center justify-center mb-2">
        <span className="text-xs text-gray-400">
          Chart preview · {chart.xColumn}
          {chart.yColumn ? ` vs ${chart.yColumn}` : ""}
        </span>
      </div>

      <div className="flex flex-wrap gap-1 mt-2">
        <span className="text-xs text-gray-400">Columns:</span>
        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
          {chart.xColumn}
        </span>
        {chart.yColumn && (
          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
            {chart.yColumn}
          </span>
        )}
      </div>
    </div>
  );
}

function SuccessScreen({ charts }: { charts: GeneratedChart[] }) {
  return (
    <div>
      <div className="text-center py-8 mb-6">
        <div className="text-5xl mb-4">📊</div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Charts ready!</h2>
        <p className="text-gray-500 text-sm">
          {charts.length} chart{charts.length !== 1 ? "s" : ""} generated from your data.
        </p>
      </div>

      {charts.length > 0 ? (
        <>
          <div className="grid gap-4 mb-6">
            {charts.map((c) => (
              <ChartPreviewCard key={c.id} chart={c} />
            ))}
          </div>
        </>
      ) : (
        <div className="text-center text-gray-400 py-8">
          <p className="text-sm">All charts were skipped — nothing to show.</p>
        </div>
      )}

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 mb-6">
        <p className="text-sm font-semibold text-blue-900 mb-1">Previous data unchanged</p>
        <p className="text-sm text-blue-700">
          Generating charts does not modify your dataset. Your previous data version is exactly as
          you left it.
        </p>
      </div>

      <a href="/" className="block text-center text-sm text-gray-500 hover:text-gray-700 underline">
        ← Back to home
      </a>
    </div>
  );
}

export function ChartReviewFlow({ charts }: { charts: ChartSuggestion[] }) {
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GeneratedChart[] | null>(null);

  const needsReview = charts.filter((c) => c.needsReview);
  const undecided = needsReview.filter((c) => !decisions[c.id]);
  const canGenerate = undecided.length === 0;

  const approved = charts.filter(
    (c) => decisions[c.id] === "approve" || (!decisions[c.id] && !c.needsReview)
  );

  function decide(id: string, d: Decision) {
    setDecisions((prev) => ({ ...prev, [id]: d }));
  }

  async function generate() {
    setGenerating(true);
    // Simulates POST /visualization-plans/{id}/generate
    await new Promise((r) => setTimeout(r, 1200));
    const generated: GeneratedChart[] = approved.map((c) => ({
      id: c.id,
      title: c.title,
      chartType: c.chartType,
      xColumn: c.xColumn,
      yColumn: c.yColumn,
      dataPoints: Math.floor(Math.random() * 200) + 20,
      description: c.whyItHelps,
    }));
    setResult(generated);
    setGenerating(false);
  }

  if (result !== null) {
    return <SuccessScreen charts={result} />;
  }

  return (
    <div>
      {/* Summary bar */}
      <div className="flex gap-4 mb-6 text-sm">
        <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex-1 text-center">
          <div className="text-xl font-bold text-gray-900">{charts.length}</div>
          <div className="text-gray-500 text-xs">Suggested charts</div>
        </div>
        <div className="bg-white border border-orange-200 rounded-lg px-4 py-3 flex-1 text-center">
          <div className="text-xl font-bold text-orange-600">{undecided.length}</div>
          <div className="text-gray-500 text-xs">Need a decision</div>
        </div>
        <div className="bg-white border border-green-200 rounded-lg px-4 py-3 flex-1 text-center">
          <div className="text-xl font-bold text-green-600">{approved.length}</div>
          <div className="text-gray-500 text-xs">Approved</div>
        </div>
      </div>

      {/* Chart suggestion cards */}
      <div className="space-y-4 mb-8">
        {charts.map((c) => (
          <ChartCard
            key={c.id}
            chart={c}
            decision={decisions[c.id] ?? null}
            onDecide={(d) => decide(c.id, d)}
          />
        ))}
      </div>

      {/* Blocked warning */}
      {undecided.length > 0 && (
        <p className="text-sm text-orange-600 mb-3 text-center">
          {undecided.length} chart{undecided.length > 1 ? "s" : ""} still need
          {undecided.length === 1 ? "s" : ""} a decision before you can continue.
        </p>
      )}

      <button
        onClick={generate}
        disabled={!canGenerate || generating}
        className={`w-full py-3 rounded-xl text-sm font-semibold transition-colors ${
          canGenerate && !generating
            ? "bg-green-600 hover:bg-green-700 text-white"
            : "bg-gray-200 text-gray-400 cursor-not-allowed"
        }`}
      >
        {generating
          ? "Creating your charts…"
          : `Create selected charts (${approved.length} approved)`}
      </button>

      <p className="mt-3 text-xs text-gray-400 text-center">
        Your previous data will not be changed.
      </p>
    </div>
  );
}
