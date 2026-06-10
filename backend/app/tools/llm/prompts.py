"""
Compact prompt builders for each LLM-assisted generation stage.

Design rules:
- Send column names + types only, never raw data values (token budget).
- One call per pipeline stage, not per column/issue.
- Tool schemas are tight — only fields the service actually uses.
"""

from typing import Any

from app.schemas.analytics_context import DatasetContext
from app.schemas.cleaning import CleaningStep
from app.schemas.profile import DataProfile


# ---------------------------------------------------------------------------
# Cleaning: enrich rationale on high-impact steps
# ---------------------------------------------------------------------------

CLEANING_ENRICH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "enriched_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string"},
                    "rationale": {"type": "string"},
                    "recommended_action": {"type": "string"},
                },
                "required": ["step_id", "rationale", "recommended_action"],
            },
        }
    },
    "required": ["enriched_steps"],
}


def cleaning_enrich_prompt(steps: list[CleaningStep], table_name: str) -> str:
    lines = [
        f"Table: {table_name}",
        "Improve the rationale and recommended_action for each high-impact cleaning step below.",
        "Be specific, concise, and business-oriented. One sentence each.",
        "",
    ]
    for s in steps:
        lines.append(
            f"- step_id={s.step_id} | col={s.issue.column_name or 'table'}"
            f" | issue={s.issue.issue_type} | affected={s.issue.affected_rows_percent:.1f}%"
            f" | current_rationale: {s.recommendation.rationale}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Features: suggest domain-specific features beyond keyword matching
# ---------------------------------------------------------------------------

FEATURE_SUGGEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "features": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "feature_name": {"type": "string"},
                    "display_name": {"type": "string"},
                    "operation_type": {
                        "type": "string",
                        "enum": [
                            "date_extract", "ratio", "window",
                            "aggregate", "encode", "custom",
                        ],
                    },
                    "formula_display": {"type": "string"},
                    "output_column": {"type": "string"},
                    "required_columns": {"type": "array", "items": {"type": "string"}},
                    "parameters": {"type": "object"},
                },
                "required": [
                    "feature_name", "display_name", "operation_type",
                    "formula_display", "output_column", "required_columns", "parameters",
                ],
            },
        }
    },
    "required": ["features"],
}


def feature_suggest_prompt(profile: DataProfile, existing_names: list[str]) -> str:
    col_lines = []
    for c in profile.column_profiles:
        roles = []
        if c.is_likely_metric:
            roles.append("metric")
        if c.is_likely_id:
            roles.append("id")
        if c.is_likely_date:
            roles.append("date")
        if c.is_likely_categorical:
            roles.append("categorical")
        role_str = "/".join(roles) if roles else "other"
        extras: list[str] = []
        if c.unique_count is not None:
            extras.append(f"{c.unique_count} distinct")
        if c.null_percent is not None and c.null_percent > 0:
            extras.append(f"{c.null_percent:.1f}% null")
        if c.top_values:
            sample = ", ".join(str(v) for v in c.top_values[:3])
            extras.append(f"sample=[{sample}]")
        extra_str = f"  [{'; '.join(extras)}]" if extras else ""
        col_lines.append(f"  {c.column_name} ({c.data_type}, {role_str}){extra_str}")

    already = ", ".join(existing_names) if existing_names else "none"
    return (
        f"Table: {profile.table_name} ({profile.row_count} rows)\n"
        f"Columns:\n" + "\n".join(col_lines) + "\n\n"
        f"Already suggested: {already}\n\n"
        "Suggest up to 4 additional derived features not already listed. "
        "Only use columns that exist in the table. "
        "Focus on business metrics, ratios, encodings, or aggregations. "
        "Return empty array if no valuable additions exist."
    )


# ---------------------------------------------------------------------------
# Charts: suggest charts for patterns the heuristic rules missed
# ---------------------------------------------------------------------------

CHART_SUGGEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "charts": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "chart_type": {
                        "type": "string",
                        "enum": ["line", "bar", "scatter", "pie", "histogram", "area"],
                    },
                    "x_column": {"type": "string"},
                    "y_column": {"type": "string"},
                    "aggregation": {"type": "string"},
                    "user_facing_explanation": {"type": "string"},
                },
                "required": [
                    "title", "description", "chart_type",
                    "x_column", "user_facing_explanation",
                ],
            },
        }
    },
    "required": ["charts"],
}


def chart_suggest_prompt(profile: DataProfile, existing_titles: list[str]) -> str:
    col_lines = []
    for c in profile.column_profiles:
        roles = []
        if c.is_likely_metric:
            roles.append("metric")
        if c.is_likely_date:
            roles.append("date")
        if c.is_likely_categorical:
            roles.append(f"categorical({c.unique_count} vals)")
        role_str = "/".join(roles) if roles else "other"
        col_lines.append(f"  {c.column_name} ({c.data_type}, {role_str})")

    already = "; ".join(existing_titles) if existing_titles else "none"
    return (
        f"Table: {profile.table_name} ({profile.row_count} rows)\n"
        f"Columns:\n" + "\n".join(col_lines) + "\n\n"
        f"Already have charts: {already}\n\n"
        "Suggest up to 3 additional charts for patterns not already covered. "
        "Only use columns that exist in the table. "
        "Return empty array if existing charts are sufficient."
    )


# ---------------------------------------------------------------------------
# Analytics planner: classify intent and select tool spec from context
# ---------------------------------------------------------------------------

ANALYTICS_PLANNER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "text_answer", "table_result", "visual_result",
                "mixed_result", "save_table_result", "save_visual_result", "unsupported",
            ],
        },
        # ── SQL path (preferred for table/mixed intents) ──────────────────
        "sql": {
            "type": "string",
            "description": (
                "A complete, read-only SELECT or WITH...SELECT query. "
                "Use this for any table/mixed intent — especially for complex patterns "
                "such as top-N per group, window functions, CTEs, subqueries, or multi-table joins. "
                "Use only table and column names listed in the schema above. "
                "Leave empty only for visual/text/save intents."
            ),
        },
        # ── Simple-aggregation fallback (used when sql is absent) ─────────
        "table_name": {"type": "string"},
        "group_by": {"type": "array", "items": {"type": "string"}},
        "metric_column": {"type": "string"},
        "aggregation": {
            "type": "string",
            "enum": ["count", "sum", "avg", "min", "max", "median"],
        },
        "filter_column": {"type": "string"},
        "filter_value": {},
        # ── Visual intent ─────────────────────────────────────────────────
        "x_column": {"type": "string"},
        "y_column": {"type": "string"},
        "chart_type": {
            "type": "string",
            "enum": ["bar", "line", "pie", "scatter", "histogram", "area"],
        },
        "suggested_title": {"type": "string"},
        "reasoning_summary": {"type": "string"},
    },
    "required": ["intent", "suggested_title", "reasoning_summary"],
}


def analytics_text_answer_prompt(question: str, context: DatasetContext) -> str:
    """
    Prompt for a conversational text answer to a meta or explanatory question.
    Sends column schema only — no raw data values.
    """
    table_lines: list[str] = []
    for t in context.tables:
        col_parts = []
        for c in t.columns:
            roles = []
            if c.is_likely_metric:
                roles.append("metric")
            if c.is_likely_date:
                roles.append("date")
            if c.is_likely_categorical:
                roles.append("categorical")
            if c.is_likely_id:
                roles.append("id")
            role_str = "/".join(roles) if roles else "other"
            col_parts.append(f"  - {c.column_name} ({c.data_type}, {role_str})")
        rows_info = f"{t.row_count} rows" if t.row_count is not None else "unknown rows"
        table_lines.append(
            f"Table: {t.table_name} ({rows_info})\n" + "\n".join(col_parts)
        )

    tables_block = "\n\n".join(table_lines) if table_lines else "(no tables available)"

    return (
        f"You are an AI data analyst assistant. "
        f"The user is working with the dataset \"{context.dataset_name}\".\n\n"
        f"Dataset schema:\n{tables_block}\n\n"
        f"User question: {question}\n\n"
        "Answer conversationally and helpfully. "
        "Focus on what the data contains, what questions can be answered, "
        "what metrics or dimensions are available, and what patterns might be worth exploring. "
        "Do not produce SQL or code. "
        "Keep the answer under 200 words."
    )


def analytics_planner_prompt(question: str, context: DatasetContext) -> str:
    table_lines: list[str] = []
    for t in context.tables:
        col_parts = []
        for c in t.columns:
            roles = []
            if c.is_likely_metric:
                roles.append("metric")
            if c.is_likely_date:
                roles.append("date")
            if c.is_likely_categorical:
                roles.append("categorical")
            if c.is_likely_id:
                roles.append("id")
            role_str = "/".join(roles) if roles else "other"
            # Append profile statistics so the LLM can make correct assumptions
            # without guessing from column names alone.
            extras: list[str] = []
            if c.unique_count is not None:
                extras.append(f"{c.unique_count} distinct")
            if c.null_percent is not None and c.null_percent > 0:
                extras.append(f"{c.null_percent:.1f}% null")
            if c.top_values:
                sample = ", ".join(str(v) for v in c.top_values[:5])
                extras.append(f"sample=[{sample}]")
            extra_str = f"  [{'; '.join(extras)}]" if extras else ""
            col_parts.append(f"    {c.column_name} ({c.data_type}, {role_str}){extra_str}")
        rows_info = f"{t.row_count} rows" if t.row_count is not None else "unknown rows"
        table_lines.append(f"  Table: {t.table_name} ({rows_info})\n" + "\n".join(col_parts))

    tables_block = "\n".join(table_lines) if table_lines else "  (no tables available)"

    return (
        f"Dataset: {context.dataset_name}\n"
        f"Tables:\n{tables_block}\n\n"
        f"User question: {question}\n\n"
        "Classify the question and write a read-only SQL SELECT query to answer it.\n"
        "Rules:\n"
        "- Use only table names and column names listed above.\n"
        "- For table_result or mixed_result intents, always populate the `sql` field with a complete query.\n"
        "- Use CTEs (WITH ...), window functions, and subqueries freely for complex patterns.\n"
        "- The query must start with SELECT or WITH. No DDL or DML keywords allowed.\n"
        "- For visual_result or text_answer intents, leave `sql` empty and fill the visual/aggregation fields.\n"
        "- If the question cannot be answered with the available data, set intent to 'unsupported'.\n\n"
        "Pattern reference — top-1 per group (\"for each X, the most popular Y\"):\n"
        "  WITH freq AS (\n"
        "    SELECT <partition_col>, <item_col>, COUNT(*) AS n\n"
        "    FROM <table> GROUP BY <partition_col>, <item_col>\n"
        "  ),\n"
        "  ranked AS (\n"
        "    SELECT *, ROW_NUMBER() OVER (PARTITION BY <partition_col> ORDER BY n DESC) AS rn\n"
        "    FROM freq\n"
        "  )\n"
        "  SELECT <partition_col>, <item_col>, n FROM ranked WHERE rn = 1 ORDER BY n DESC"
    )
