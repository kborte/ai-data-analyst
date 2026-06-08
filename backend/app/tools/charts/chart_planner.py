"""
Deterministic chart planner: produces up to MAX_SUGGESTIONS ChartSuggestion
objects from a DataProfile using fixed heuristic rules. No LLM calls.

Rules applied in priority order:
  1. line  — date column + metric column
  2. bar   — categorical column + metric column (sum by category)
  3. bar   — categorical column alone (count by category)
  4. pie   — low-cardinality categorical column (unique_count ≤ PIE_MAX_CARDINALITY)
  5. scatter — any two metric columns
"""

from uuid import uuid4

from app.schemas.common import ChartType
from app.schemas.profile import DataProfile
from app.schemas.visualization import ChartSuggestion

MAX_SUGGESTIONS = 8
PIE_MAX_CARDINALITY = 5


class ChartPlanner:
    def suggest(self, profile: DataProfile) -> list[ChartSuggestion]:
        date_cols = [c for c in profile.column_profiles if c.is_likely_date and not c.is_likely_id]
        metric_cols = [c for c in profile.column_profiles if c.is_likely_metric and not c.is_likely_id]
        cat_cols = [c for c in profile.column_profiles if c.is_likely_categorical and not c.is_likely_id]

        suggestions: list[ChartSuggestion] = []

        # Rule 1: line — date + metric
        for date_col in date_cols:
            for metric_col in metric_cols:
                suggestions.append(
                    ChartSuggestion(
                        visualization_id=uuid4(),
                        title=f"{metric_col.column_name.replace('_', ' ').title()} over time",
                        description=(
                            f"How {metric_col.column_name} changes over {date_col.column_name}."
                        ),
                        chart_type=ChartType.line,
                        input_table=profile.table_name,
                        x_column=date_col.column_name,
                        y_column=metric_col.column_name,
                        aggregation="sum",
                        sort="asc",
                        user_facing_explanation=(
                            f"Shows the trend of {metric_col.column_name} over time."
                        ),
                    )
                )

        # Rule 2: bar — category + metric
        for cat_col in cat_cols:
            for metric_col in metric_cols:
                suggestions.append(
                    ChartSuggestion(
                        visualization_id=uuid4(),
                        title=(
                            f"{metric_col.column_name.replace('_', ' ').title()}"
                            f" by {cat_col.column_name.replace('_', ' ').title()}"
                        ),
                        description=(
                            f"Total {metric_col.column_name} broken down"
                            f" by {cat_col.column_name}."
                        ),
                        chart_type=ChartType.bar,
                        input_table=profile.table_name,
                        x_column=cat_col.column_name,
                        y_column=metric_col.column_name,
                        aggregation="sum",
                        sort="desc",
                        user_facing_explanation=(
                            f"Compares {metric_col.column_name}"
                            f" across {cat_col.column_name} categories."
                        ),
                    )
                )

        # Rule 3: bar — category count
        for cat_col in cat_cols:
            suggestions.append(
                ChartSuggestion(
                    visualization_id=uuid4(),
                    title=f"Count by {cat_col.column_name.replace('_', ' ').title()}",
                    description=f"Number of records for each {cat_col.column_name} value.",
                    chart_type=ChartType.bar,
                    input_table=profile.table_name,
                    x_column=cat_col.column_name,
                    aggregation="count",
                    sort="desc",
                    limit=20,
                    user_facing_explanation=(
                        f"Shows how many rows exist per {cat_col.column_name} category."
                    ),
                )
            )

        # Rule 4: pie — low-cardinality category only
        for cat_col in cat_cols:
            if cat_col.unique_count <= PIE_MAX_CARDINALITY:
                suggestions.append(
                    ChartSuggestion(
                        visualization_id=uuid4(),
                        title=f"Share by {cat_col.column_name.replace('_', ' ').title()}",
                        description=f"Part-to-whole breakdown for {cat_col.column_name}.",
                        chart_type=ChartType.pie,
                        input_table=profile.table_name,
                        x_column=cat_col.column_name,
                        aggregation="count",
                        user_facing_explanation=(
                            f"Shows the proportion of records per {cat_col.column_name}."
                        ),
                    )
                )

        # Rule 5: scatter — two metric columns
        for i, col_a in enumerate(metric_cols):
            for col_b in metric_cols[i + 1 :]:
                suggestions.append(
                    ChartSuggestion(
                        visualization_id=uuid4(),
                        title=(
                            f"{col_a.column_name.replace('_', ' ').title()}"
                            f" vs {col_b.column_name.replace('_', ' ').title()}"
                        ),
                        description=(
                            f"Relationship between {col_a.column_name}"
                            f" and {col_b.column_name}."
                        ),
                        chart_type=ChartType.scatter,
                        input_table=profile.table_name,
                        x_column=col_a.column_name,
                        y_column=col_b.column_name,
                        user_facing_explanation=(
                            f"Explores correlation between {col_a.column_name}"
                            f" and {col_b.column_name}."
                        ),
                    )
                )

        return suggestions[:MAX_SUGGESTIONS]
