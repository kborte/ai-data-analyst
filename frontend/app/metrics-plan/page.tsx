import Link from "next/link";
import { MetricSuggestion, MetricsReviewFlow } from "../components/MetricsReviewFlow";

const SUGGESTED_METRICS: MetricSuggestion[] = [
  {
    id: "aov",
    displayName: "Average Order Value (AOV)",
    formulaDisplay: "revenue ÷ number of orders",
    whyItHelps:
      "Tells you how much a typical order is worth. Useful for tracking whether customers are spending more or less over time.",
    requiredColumns: ["revenue", "order_count"],
    needsReview: true,
  },
  {
    id: "running_revenue",
    displayName: "Running Revenue",
    formulaDisplay: "cumulative sum of revenue, ordered by date",
    whyItHelps:
      "Shows how total revenue builds up over time — makes it easy to spot growth spurts, plateaus, or slowdowns at a glance.",
    requiredColumns: ["date", "revenue"],
    needsReview: true,
  },
  {
    id: "revenue_by_channel",
    displayName: "Revenue by Channel",
    formulaDisplay: "sum of revenue, grouped by channel",
    whyItHelps:
      "Breaks down which channels are driving the most revenue. Helps you see where to invest more — or cut back.",
    requiredColumns: ["channel", "revenue"],
    needsReview: true,
  },
  {
    id: "date_parts",
    displayName: "Date Parts from Order Date",
    formulaDisplay: "year, month, week number, and weekday extracted from order_date",
    whyItHelps:
      "Makes it easy to filter or group your data by time period — for example, to see monthly trends or compare weekday vs weekend sales.",
    requiredColumns: ["order_date"],
    needsReview: true,
  },
];

export default function MetricsPlanPage() {
  return (
    <main className="min-h-screen bg-gray-50 py-16 px-6">
      <div className="max-w-3xl mx-auto">
        <div className="mb-8">
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">
            ← Back
          </Link>
        </div>

        <h1 className="text-3xl font-bold text-gray-900 mb-2">Suggested metrics</h1>
        <p className="text-gray-500 mb-8 text-sm">
          Based on your data, we found a few useful metrics you can add. Review each one, approve
          the ones you want calculated, and skip any you don&apos;t need.
        </p>

        <MetricsReviewFlow metrics={SUGGESTED_METRICS} />
      </div>
    </main>
  );
}
