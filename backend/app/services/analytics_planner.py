"""M12D: Lightweight analytics planner service.

Rule-based intent classification + context-aware tool spec building.
Optional LLM enhancement: LLM suggests table/column choices; deterministic
code validates them against the dataset context and executes the plan.

Recent messages are consumed for follow-up resolution and never persisted.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from app.schemas.analytics import (
    AggregateTableSpec,
    AllowedAggregation,
    AnalyticsIntent,
    AnalyticsPlan,
    FilterOperator,
    FilterSpec,
    FilterTableSpec,
    GenerateVisualSpec,
    MetricSpec,
    MixedOutput,
    OutputType,
    PreviewTableSpec,
    PriorOutputRef,
    RecentMessage,
    SaveTableResultSpec,
    SaveVisualResultSpec,
    TableOutput,
    TextOutput,
    VisualOutput,
)
from app.schemas.analytics_context import DatasetContext, DatasetContextTable
from app.tools.analytics.query_tools import (
    AnalyticsToolError,
    run_aggregate_table,
    run_filter_table,
    run_generate_visual,
    run_preview_table,
    run_simple_join,
)
from app.tools.llm.prompts import (
    ANALYTICS_PLANNER_SCHEMA,
    analytics_planner_prompt,
    analytics_text_answer_prompt,
)
from app.tools.llm.provider import FakeLLMProvider, LLMProvider

# ---------------------------------------------------------------------------
# Intent classification constants
# ---------------------------------------------------------------------------

_VISUAL_WORDS = frozenset([
    "chart", "plot", "graph", "visual", "visualise", "visualize",
    "bar", "line", "pie", "scatter", "histogram",
])

# Explicit chart keywords that unambiguously indicate a visual request.
_EXPLICIT_CHART_WORDS = frozenset(["chart", "plot", "graph", "visualize", "visualise", "histogram"])
_AGGREGATE_WORDS = frozenset([
    "sum", "total", "aggregate", "group", "breakdown", "by",
    "average", "avg", "mean", "count", "median", "min", "max",
    "revenue by", "sales by", "grouped",
])
_TABLE_WORDS = frozenset([
    "table", "list", "show", "top", "rank", "filter", "where",
    "join", "compare", "pivot", "breakdown",
    "most", "least", "popular", "best", "worst", "highest", "lowest",
    "biggest", "smallest", "largest", "frequent", "common", "leading",
])
_TEXT_WORDS = frozenset([
    "why", "how", "explain", "describe", "tell", "summary",
    "insight", "analyze", "analyse", "define", "overview",
])
_SAVE_WORDS = frozenset(["save", "keep", "store", "bookmark"])


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

def classify_intent(
    question: str,
    prior_refs: list[PriorOutputRef],
) -> AnalyticsIntent:
    q_lower = question.lower()
    w = _words(q_lower)

    # Save intents require an explicit save word AND a prior output ref.
    if _SAVE_WORDS & w and prior_refs:
        visual_refs = [r for r in prior_refs if r.output_type == OutputType.visual]
        table_refs = [r for r in prior_refs if r.output_type == OutputType.table]
        if visual_refs:
            return AnalyticsIntent.save_visual_result
        if table_refs:
            return AnalyticsIntent.save_table_result

    # Follow-up: "show as chart" / "now plot this" with prior table ref
    follow_up_visual_phrases = [
        "as a chart", "as chart", "as a graph", "as visual",
        "show chart", "plot this", "visualize this", "visualise this",
        "now chart", "now plot",
    ]
    if any(phrase in q_lower for phrase in follow_up_visual_phrases):
        if any(r.output_type == OutputType.table for r in prior_refs):
            return AnalyticsIntent.visual_result

    # Explicit chart words unambiguously indicate a visual request.
    if _EXPLICIT_CHART_WORDS & w:
        return AnalyticsIntent.visual_result

    visual_score = sum(1 for kw in _VISUAL_WORDS if kw in q_lower)
    agg_score = sum(1 for kw in _AGGREGATE_WORDS if kw in q_lower)
    table_score = sum(1 for kw in _TABLE_WORDS if kw in q_lower)
    text_score = sum(1 for kw in _TEXT_WORDS if kw in q_lower)

    # Mixed: has both a visual keyword and a table/aggregate keyword
    if visual_score >= 1 and (agg_score + table_score) >= 1:
        return AnalyticsIntent.mixed_result

    if visual_score >= 1:
        return AnalyticsIntent.visual_result

    if agg_score >= 1:
        return AnalyticsIntent.table_result

    if table_score >= 1:
        return AnalyticsIntent.table_result

    if text_score >= 1:
        return AnalyticsIntent.text_answer

    # Default to a table result — most unanswered questions in a data app want data.
    return AnalyticsIntent.table_result


# ---------------------------------------------------------------------------
# Rule-based tool spec builder
# ---------------------------------------------------------------------------

def _intent_to_output_type(intent: AnalyticsIntent) -> OutputType:
    match intent:
        case AnalyticsIntent.table_result | AnalyticsIntent.save_table_result:
            return OutputType.table
        case AnalyticsIntent.visual_result | AnalyticsIntent.save_visual_result:
            return OutputType.visual
        case AnalyticsIntent.mixed_result:
            return OutputType.mixed
        case _:
            return OutputType.text


_COUNT_WORDS = frozenset([
    "popular", "frequent", "common", "count", "times", "often", "top",
])
# Words that signal "give me the highest value" — use max aggregation
_MAX_WORDS = frozenset(["maximum", "biggest", "largest", "most"])
_MIN_WORDS = frozenset(["minimum", "smallest", "least"])
_AVG_WORDS = frozenset(["average", "avg", "mean"])


def _detect_aggregation(question: str) -> "AllowedAggregation":
    """Choose the aggregation function based on question keywords."""
    w = _words(question)
    if w & _COUNT_WORDS:
        return AllowedAggregation.count
    if w & _AVG_WORDS:
        return AllowedAggregation.avg
    if w & _MIN_WORDS:
        return AllowedAggregation.min
    if w & _MAX_WORDS:
        return AllowedAggregation.max
    return AllowedAggregation.sum


# Table name keywords that suggest a primary analytical table over a lookup table.
_ANALYTICAL_TABLE_WORDS = frozenset([
    "sales", "orders", "transactions", "revenue", "customers", "products",
    "events", "sessions", "leads", "bookings", "payments",
])
# Table name keywords that suggest a lookup/reference table (lower priority).
_LOOKUP_TABLE_WORDS = frozenset([
    "codes", "lookup", "reference", "mapping", "dim", "meta",
])


def _best_table_for_question(question: str, context: DatasetContext) -> "DatasetContextTable | None":
    """Return the table whose columns (or name) best match the question's domain keywords."""
    if not context.tables:
        return None
    q_words = _words(question)

    def _score(table: "DatasetContextTable") -> tuple[int, int]:
        col_names_lower = {c.column_name.lower() for c in table.columns}
        tname_lower = table.table_name.lower()
        keyword_hits = 0

        # Score by column name matches (works when profile exists)
        for kw_set, col_hints in _KEYWORD_COL_HINTS:
            if kw_set & q_words:
                for hint in col_hints:
                    if any(hint in cn for cn in col_names_lower):
                        keyword_hits += 1

        # Score by table name (works even without a profile)
        for word in _ANALYTICAL_TABLE_WORDS:
            if word in tname_lower:
                keyword_hits += 2
        for word in _LOOKUP_TABLE_WORDS:
            if word in tname_lower:
                keyword_hits -= 2

        has_metrics = int(any(c.is_likely_metric for c in table.columns))
        return (keyword_hits + has_metrics, table.row_count or 0)

    return max(context.tables, key=_score)


def _first_table(context: DatasetContext) -> "DatasetContextTable | None":
    return context.tables[0] if context.tables else None


def _metric_cols(table: DatasetContextTable) -> list[str]:
    cols = [c.column_name for c in table.columns if c.is_likely_metric]
    if not cols and table.columns:
        cols = [table.columns[-1].column_name]
    return cols


def _groupby_cols(table: DatasetContextTable) -> list[str]:
    cols = [
        c.column_name for c in table.columns
        if c.is_likely_categorical or c.is_likely_date
    ]
    if not cols and table.columns:
        cols = [table.columns[0].column_name]
    return cols


def _chart_type_from_question(question: str) -> str:
    q = question.lower()
    if "pie" in q:
        return "pie"
    if "scatter" in q or "correlation" in q:
        return "scatter"
    if "line" in q or "trend" in q or "over time" in q:
        return "line"
    return "bar"


# Maps question keywords to substrings that should appear in column names.
# Ordered from most specific to least specific within each group.
_KEYWORD_COL_HINTS: list[tuple[frozenset[str], list[str]]] = [
    (frozenset(["country", "countries", "nation", "nations"]),   ["country", "nation"]),
    (frozenset(["state", "states", "region", "regions"]),        ["state", "region"]),
    (frozenset(["city", "cities"]),                              ["city"]),
    (frozenset(["product", "products", "item", "items", "sku"]), ["product", "item", "sku", "category"]),
    (frozenset(["channel", "channels", "touchpoint"]),           ["channel", "touchpoint"]),
    (frozenset(["customer", "customers", "segment"]),            ["customer", "segment", "cust"]),
    (frozenset(["gender"]),                                      ["gender"]),
    (frozenset(["generation"]),                                  ["generation"]),
    (frozenset(["status"]),                                      ["status"]),
    (frozenset(["type"]),                                        ["type"]),
]

# Temporal period keywords: question word → date_trunc_period value
_TEMPORAL_KEYWORDS: dict[str, str] = {
    "month":   "month",
    "monthly": "month",
    "months":  "month",
    "year":    "year",
    "yearly":  "year",
    "annual":  "year",
    "annually":"year",
    "years":   "year",
    "week":    "week",
    "weekly":  "week",
    "weeks":   "week",
    "quarter": "quarter",
    "quarterly":"quarter",
    "quarters":"quarter",
    "day":     "day",
    "daily":   "day",
    "days":    "day",
}


def _detect_temporal_period(question: str) -> str | None:
    """Return the date truncation period implied by the question, or None."""
    for word in _words(question):
        if word in _TEMPORAL_KEYWORDS:
            return _TEMPORAL_KEYWORDS[word]
    return None


def _question_hinted_groupby(
    question: str,
    table: "DatasetContextTable",
    fallback: list[str],
) -> list[str]:
    """
    Return up to 2 columns that best match the question's grouping keywords.
    Temporal keywords (month/year/week/…) map to date columns.
    Domain keywords (country/state/…) map to matching categorical columns.
    Falls back to the default categorical columns when no keyword matches.
    """
    q_words = _words(question)
    cat_col_names = {c.column_name for c in table.columns if c.is_likely_categorical}
    date_col_names = [c.column_name for c in table.columns if c.is_likely_date]
    all_col_names_lower = {c.column_name.lower(): c.column_name for c in table.columns}

    # Temporal period: "by month" / "over time" → pick the primary date column
    if _detect_temporal_period(question) and date_col_names:
        # Prefer ORDER_DATE / date / created_at style; take first date column
        preferred = next(
            (c for c in date_col_names if "order" in c.lower() or "date" in c.lower()),
            date_col_names[0],
        )
        return [preferred]

    chosen: list[str] = []
    for kw_set, col_hints in _KEYWORD_COL_HINTS:
        if not (kw_set & q_words):
            continue
        for hint in col_hints:
            matched = [
                orig for lower, orig in all_col_names_lower.items()
                if hint in lower and orig in cat_col_names and orig not in chosen
            ]
            chosen.extend(matched)
        if len(chosen) >= 2:
            break

    return chosen[:2] if chosen else fallback[:2]


def _build_rule_based_spec(
    intent: AnalyticsIntent,
    question: str,
    context: DatasetContext,
    prior_refs: list[PriorOutputRef],
) -> Any:
    """Return a ToolSpec for the given intent using rule-based heuristics."""
    if intent in (AnalyticsIntent.save_table_result, AnalyticsIntent.save_visual_result):
        ref = next(
            (r for r in prior_refs if r.output_type in (OutputType.table, OutputType.visual)),
            None,
        )
        ref_id = ref.output_id if ref else uuid.uuid4()
        if intent == AnalyticsIntent.save_table_result:
            return SaveTableResultSpec(output_id=ref_id, name="Saved view")
        return SaveVisualResultSpec(output_id=ref_id, title="Saved visual")

    # Pick the table most relevant to the question, not just the first one.
    table = _best_table_for_question(question, context) or _first_table(context)

    if table is None:
        return PreviewTableSpec(table_name="unknown")

    if intent == AnalyticsIntent.visual_result:
        visual_table = _best_table_for_question(question, context) or table
        gb = _groupby_cols(visual_table)
        metrics = _metric_cols(visual_table)
        return GenerateVisualSpec(
            table_name=visual_table.table_name,
            chart_type=_chart_type_from_question(question),
            x_column=gb[0] if gb else visual_table.columns[0].column_name,
            y_column=metrics[0] if metrics else None,
        )

    if intent in (AnalyticsIntent.table_result, AnalyticsIntent.mixed_result):
        default_gb = _groupby_cols(table)
        gb = _question_hinted_groupby(question, table, default_gb)
        metrics = _metric_cols(table)
        agg = _detect_aggregation(question)

        # For count aggregation use a non-null categorical col (the group-by col itself works).
        if agg == AllowedAggregation.count:
            metric_col = gb[0] if gb else (metrics[0] if metrics else None)
        else:
            metric_col = metrics[0] if metrics else None

        if gb and metric_col:
            period = _detect_temporal_period(question)
            # The aggregated result column is named "{agg}_{metric_col}" by run_aggregate_table.
            agg_col_name = f"{agg}_{metric_col}"
            sort_by = gb[0] if period else agg_col_name
            return AggregateTableSpec(
                table_name=table.table_name,
                group_by=gb,
                metrics=[MetricSpec(column=metric_col, aggregation=agg)],
                sort_by=sort_by,
                sort_desc=False if period else True,
                date_trunc_period=period,
            )
        return PreviewTableSpec(table_name=table.table_name)

    # text_answer / unsupported → preview
    return PreviewTableSpec(table_name=table.table_name if table else "unknown")


# ---------------------------------------------------------------------------
# LLM enhancement: suggest table/column choices; validate before trusting
# ---------------------------------------------------------------------------

def _apply_llm_hint(
    llm_raw: dict[str, Any],
    intent: AnalyticsIntent,
    context: DatasetContext,
) -> Any | None:
    """Build a validated ToolSpec from the LLM's raw response, or return None."""
    if not llm_raw:
        return None

    table_name = llm_raw.get("table_name", "")
    valid_tables = {t.table_name for t in context.tables}
    if table_name not in valid_tables:
        return None

    ctx_table = next(t for t in context.tables if t.table_name == table_name)
    valid_cols = {c.column_name for c in ctx_table.columns}

    def _valid_col(name: str | None) -> str | None:
        return name if name and name in valid_cols else None

    def _valid_cols(names: list[str]) -> list[str]:
        return [n for n in names if n in valid_cols]

    try:
        if intent == AnalyticsIntent.visual_result:
            x = _valid_col(llm_raw.get("x_column")) or (
                ctx_table.columns[0].column_name if ctx_table.columns else None
            )
            if not x:
                return None
            return GenerateVisualSpec(
                table_name=table_name,
                chart_type=llm_raw.get("chart_type", "bar"),
                x_column=x,
                y_column=_valid_col(llm_raw.get("y_column")),
            )

        if intent in (AnalyticsIntent.table_result, AnalyticsIntent.mixed_result):
            gb = _valid_cols(llm_raw.get("group_by") or [])
            metric = _valid_col(llm_raw.get("metric_column"))
            agg_raw = llm_raw.get("aggregation", "sum")
            try:
                agg = AllowedAggregation(agg_raw)
            except ValueError:
                agg = AllowedAggregation.sum
            # For count, use the group-by column as the metric if no metric provided.
            if not metric and agg == AllowedAggregation.count and gb:
                metric = gb[0]
            if gb and metric:
                agg_col_name = f"{agg}_{metric}"
                return AggregateTableSpec(
                    table_name=table_name,
                    group_by=gb,
                    metrics=[MetricSpec(column=metric, aggregation=agg)],
                    sort_by=agg_col_name,
                    sort_desc=True,
                )
            # LLM couldn't provide useful columns — let rule-based spec stand.
            return None

    except Exception:  # noqa: BLE001
        return None

    return None


# ---------------------------------------------------------------------------
# Main planner class
# ---------------------------------------------------------------------------

class AnalyticsPlanner:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm or FakeLLMProvider()

    def plan(
        self,
        question: str,
        context: DatasetContext,
        recent_messages: list[RecentMessage] | None = None,
        prior_output_refs: list[PriorOutputRef] | None = None,
    ) -> AnalyticsPlan:
        """Classify the question and return a validated structured plan.

        recent_messages are used only to extract prior output refs for
        follow-up resolution. They are never persisted.
        """
        recent_messages = recent_messages or []
        prior_output_refs = prior_output_refs or []

        # Collect all output refs: top-level + from recent message history
        all_refs: list[PriorOutputRef] = list(prior_output_refs)
        for msg in recent_messages:
            all_refs.extend(msg.output_refs)

        intent = classify_intent(question, all_refs)

        # Rule-based spec (always safe fallback)
        tool_spec = _build_rule_based_spec(intent, question, context, all_refs)

        # Optional LLM enhancement
        if self._llm.is_available() and intent not in (
            AnalyticsIntent.save_table_result,
            AnalyticsIntent.save_visual_result,
            AnalyticsIntent.unsupported,
        ):
            prompt = analytics_planner_prompt(question, context)
            raw = self._llm.complete_structured(prompt, "analytics_plan", ANALYTICS_PLANNER_SCHEMA)
            llm_spec = _apply_llm_hint(raw, intent, context)
            if llm_spec is not None:
                tool_spec = llm_spec

        reasoning = (
            f"Classified as '{intent}' based on question keywords and dataset context."
        )
        title = _infer_title(question, intent, tool_spec)

        return AnalyticsPlan(
            intent=intent,
            question=question,
            dataset_id=context.dataset_id,
            dataset_version_id=context.dataset_version_id,
            reasoning_summary=reasoning,
            tool_name=tool_spec.tool_name,
            tool_spec=tool_spec,
            expected_output_type=_intent_to_output_type(intent),
            suggested_title=title,
            prior_output_ref=all_refs[0] if all_refs else None,
        )

    def execute(
        self,
        plan: AnalyticsPlan,
        db_path: Path,
        workspace_id: UUID | None = None,
        dataset_id: UUID | None = None,
        storage: Any = None,
        view_repo: Any = None,
        visual_repo: Any = None,
        context: "DatasetContext | None" = None,
    ) -> TextOutput | TableOutput | VisualOutput | MixedOutput:
        """Run M12C tools for the plan. Nothing is saved automatically."""
        version_id = plan.dataset_version_id
        title = plan.suggested_title

        if plan.intent == AnalyticsIntent.unsupported:
            return TextOutput(
                dataset_version_id=version_id,
                title="Unsupported request",
                content=(
                    "This question is outside the supported analytics scope. "
                    "Try asking for a table summary, chart, or aggregation over the dataset."
                ),
            )

        if plan.intent == AnalyticsIntent.save_table_result:
            return _execute_save_table(plan, version_id, title, view_repo)

        if plan.intent == AnalyticsIntent.save_visual_result:
            return _execute_save_visual(plan, version_id, title, visual_repo)

        # For conversational/explanatory questions, call the LLM directly instead
        # of running a data tool and dumping raw rows into a text response.
        if plan.intent == AnalyticsIntent.text_answer:
            return self._execute_text_answer(plan, context, version_id, title)

        common = dict(
            db_path=db_path,
            dataset_version_id=version_id,
            title=title,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            storage=storage,
        )

        try:
            spec = plan.tool_spec
            match spec.tool_name:
                case "preview_table":
                    return run_preview_table(spec=spec, **common)
                case "aggregate_table":
                    return run_aggregate_table(spec=spec, **common)
                case "filter_table":
                    return run_filter_table(spec=spec, **common)
                case "simple_join":
                    return run_simple_join(spec=spec, **common)
                case "generate_visual":
                    return run_generate_visual(
                        db_path=db_path,
                        spec=spec,
                        dataset_version_id=version_id,
                        title=title,
                    )
                case _:
                    return TextOutput(
                        dataset_version_id=version_id,
                        title="Error",
                        content=f"Unknown tool: {spec.tool_name}",
                    )

        except AnalyticsToolError as exc:
            return TextOutput(
                dataset_version_id=version_id,
                title="Tool error",
                content=str(exc),
            )

    def _execute_text_answer(
        self,
        plan: AnalyticsPlan,
        context: "DatasetContext | None",
        version_id: UUID,
        title: str,
    ) -> TextOutput:
        if context is not None and self._llm.is_available():
            prompt = analytics_text_answer_prompt(plan.question, context)
            answer = self._llm.complete_text(prompt, max_tokens=400)
            if answer:
                return TextOutput(dataset_version_id=version_id, title=title, content=answer)

        # LLM unavailable or returned nothing — build a schema-based summary.
        if context is None or not context.tables:
            return TextOutput(
                dataset_version_id=version_id,
                title=title,
                content="No dataset context available to answer this question.",
            )
        parts: list[str] = [f'Dataset "{context.dataset_name}" contains:']
        for t in context.tables:
            rows_info = f"{t.row_count} rows" if t.row_count is not None else "an unknown number of rows"
            metrics = [c.column_name for c in t.columns if c.is_likely_metric]
            cats = [c.column_name for c in t.columns if c.is_likely_categorical]
            dates = [c.column_name for c in t.columns if c.is_likely_date]
            parts.append(f'\nTable "{t.table_name}" — {rows_info}, {len(t.columns)} columns.')
            if metrics:
                parts.append(f"  Metrics you can aggregate: {', '.join(metrics[:6])}.")
            if cats:
                parts.append(f"  Dimensions to group by: {', '.join(cats[:6])}.")
            if dates:
                parts.append(f"  Date columns for time-series: {', '.join(dates[:3])}.")
        return TextOutput(
            dataset_version_id=version_id,
            title=title,
            content=" ".join(parts),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_title(question: str, intent: AnalyticsIntent, tool_spec: Any) -> str:
    table = getattr(tool_spec, "table_name", "")
    match intent:
        case AnalyticsIntent.table_result:
            return f"Analysis: {table}" if table else question[:60]
        case AnalyticsIntent.visual_result:
            return f"Chart: {table}" if table else question[:60]
        case AnalyticsIntent.mixed_result:
            return f"Summary: {table}" if table else question[:60]
        case AnalyticsIntent.save_table_result:
            return "Save view"
        case AnalyticsIntent.save_visual_result:
            return "Save visual"
        case AnalyticsIntent.unsupported:
            return "Unsupported request"
        case _:
            return question[:60]


def _table_to_text(table: TableOutput, version_id: UUID, title: str) -> TextOutput:
    row_info = f"{table.row_count} rows"
    col_info = ", ".join(table.columns[:5])
    content = f"Result: {row_info} with columns: {col_info}."
    if table.preview_rows:
        first = dict(zip(table.columns, table.preview_rows[0]))
        content += f" First row: {first}."
    return TextOutput(
        dataset_version_id=version_id,
        title=title,
        content=content,
    )


def _execute_save_table(
    plan: AnalyticsPlan,
    version_id: UUID,
    title: str,
    view_repo: Any,
) -> TextOutput:
    if view_repo is None or plan.prior_output_ref is None:
        return TextOutput(
            dataset_version_id=version_id,
            title=title,
            content=(
                "No prior table output reference found. "
                "Generate a table result first, then ask to save it."
            ),
        )
    spec = plan.tool_spec
    name = getattr(spec, "name", "Saved view")
    return TextOutput(
        dataset_version_id=version_id,
        title=title,
        content=f"Table output '{name}' queued for saving. Call the save-as-view endpoint with output_id={plan.prior_output_ref.output_id}.",
    )


def _execute_save_visual(
    plan: AnalyticsPlan,
    version_id: UUID,
    title: str,
    visual_repo: Any,
) -> TextOutput:
    if visual_repo is None or plan.prior_output_ref is None:
        return TextOutput(
            dataset_version_id=version_id,
            title=title,
            content=(
                "No prior visual output reference found. "
                "Generate a chart first, then ask to save it."
            ),
        )
    spec = plan.tool_spec
    saved_title = getattr(spec, "title", "Saved visual")
    return TextOutput(
        dataset_version_id=version_id,
        title=title,
        content=f"Visual '{saved_title}' queued for saving. Call the save-as-visual endpoint with output_id={plan.prior_output_ref.output_id}.",
    )
