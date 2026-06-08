import Link from "next/link";
import { ChartSuggestion, ChartReviewFlow } from "../components/ChartReviewFlow";

const SUGGESTED_CHARTS: ChartSuggestion[] = [
  {
    id: "revenue-over-time",
    title: "Revenue over time",
    chartType: "line",
    inputTable: "orders",
    xColumn: "order_date",
    yColumn: "revenue",
    whyItHelps:
      "Shows how revenue changes day by day or month by month. Makes it easy to spot growth trends, seasonal dips, or one-off spikes at a glance.",
    needsReview: true,
  },
  {
    id: "revenue-by-region",
    title: "Revenue by region",
    chartType: "bar",
    inputTable: "orders",
    xColumn: "region",
    yColumn: "revenue",
    whyItHelps:
      "Compares how much revenue each region contributes. Helps you see which markets are performing well and which may need more attention.",
    needsReview: true,
  },
  {
    id: "orders-by-region",
    title: "Number of orders by region",
    chartType: "bar",
    inputTable: "orders",
    xColumn: "region",
    whyItHelps:
      "Shows how many orders came from each region — separate from revenue. Useful for spotting regions with high order volume but low average value.",
    needsReview: true,
  },
  {
    id: "share-by-channel",
    title: "Share of orders by channel",
    chartType: "pie",
    inputTable: "orders",
    xColumn: "channel",
    whyItHelps:
      "Breaks down what portion of orders come from each sales channel (e.g. online, in-store, wholesale). Helpful for understanding channel mix.",
    needsReview: true,
  },
  {
    id: "revenue-vs-cost",
    title: "Revenue vs cost",
    chartType: "scatter",
    inputTable: "orders",
    xColumn: "revenue",
    yColumn: "cost",
    whyItHelps:
      "Plots each order's revenue against its cost. Outliers here can reveal unusually profitable or unprofitable orders worth investigating.",
    needsReview: true,
  },
];

export default function ChartsPreviewPage() {
  return (
    <main className="min-h-screen bg-gray-50 py-16 px-6">
      <div className="max-w-3xl mx-auto">
        <div className="mb-8">
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">
            ← Back
          </Link>
        </div>

        <h1 className="text-3xl font-bold text-gray-900 mb-2">Suggested charts</h1>
        <p className="text-gray-500 mb-8 text-sm">
          Based on your data, we found a few charts that could reveal useful patterns. Review each
          one, approve the charts you want, and skip any you don&apos;t need.
        </p>

        <ChartReviewFlow charts={SUGGESTED_CHARTS} />
      </div>
    </main>
  );
}
