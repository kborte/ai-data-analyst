import Link from "next/link";
import { CleaningReviewFlow, SuggestedFix } from "../components/CleaningReviewFlow";

const SUGGESTED_FIXES: SuggestedFix[] = [
  {
    id: "fix-001",
    whatWasFound: "12 rows are missing a revenue value (12% of your data)",
    whyItMatters: "Rows without revenue can't be included in sales totals or averages, and would silently skew your results.",
    suggestedAction: "Remove rows where revenue is blank",
    riskLevel: "high",
    needsReview: true,
    affectedPercent: 12.0,
  },
  {
    id: "fix-002",
    whatWasFound: "8 duplicate rows found — the same entry appears more than once",
    whyItMatters: "Duplicates inflate counts and totals, making your data look bigger than it is.",
    suggestedAction: "Remove the duplicate rows, keeping one copy of each",
    riskLevel: "high",
    needsReview: true,
    affectedPercent: 8.0,
  },
  {
    id: "fix-003",
    whatWasFound: "4 rows have a blank customer segment (4% of your data)",
    whyItMatters: "Blank segments can cause rows to be missed when filtering or grouping by segment.",
    suggestedAction: 'Fill blank segments with "Unknown" so no rows are dropped',
    riskLevel: "low",
    needsReview: false,
    affectedPercent: 4.0,
  },
  {
    id: "fix-004",
    whatWasFound: 'Country names have extra spaces (e.g. "  United States  ")',
    whyItMatters: "Extra spaces make the same country look like different values, breaking grouping and counts.",
    suggestedAction: "Remove the extra spaces from country names",
    riskLevel: "low",
    needsReview: false,
    affectedPercent: 22.0,
  },
  {
    id: "fix-005",
    whatWasFound: "Order dates are stored as text, not as real dates",
    whyItMatters: "Text dates can't be sorted, filtered by range, or used in time-based charts.",
    suggestedAction: "Convert order dates to proper date format",
    riskLevel: "medium",
    needsReview: true,
    affectedPercent: 100.0,
  },
];

export default function CleaningPlanPage() {
  return (
    <main className="min-h-screen bg-gray-50 py-16 px-6">
      <div className="max-w-3xl mx-auto">
        <div className="mb-8">
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">
            ← Back
          </Link>
        </div>

        <h1 className="text-3xl font-bold text-gray-900 mb-2">Suggested fixes</h1>
        <p className="text-gray-500 mb-8 text-sm">
          We found a few issues in your data. Review each suggested fix, approve the ones you want
          applied, and skip any you'd like to leave as-is.
        </p>

        <CleaningReviewFlow fixes={SUGGESTED_FIXES} />
      </div>
    </main>
  );
}
