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
from app.tools.llm.prompts import ANALYTICS_PLANNER_SCHEMA, analytics_planner_prompt
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
])
_TEXT_WORDS = frozenset([
    "what", "why", "how", "explain", "describe", "tell", "summary",
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

    return AnalyticsIntent.unsupported


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


def _first_table(context: DatasetContext) -> DatasetContextTable | None:
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


def _build_rule_based_spec(
    intent: AnalyticsIntent,
    question: str,
    context: DatasetContext,
    prior_refs: list[PriorOutputRef],
) -> Any:
    """Return a ToolSpec for the given intent using rule-based heuristics."""
    table = _first_table(context)

    if intent in (AnalyticsIntent.save_table_result, AnalyticsIntent.save_visual_result):
        ref = next(
            (r for r in prior_refs if r.output_type in (OutputType.table, OutputType.visual)),
            None,
        )
        ref_id = ref.output_id if ref else uuid.uuid4()
        if intent == AnalyticsIntent.save_table_result:
            return SaveTableResultSpec(output_id=ref_id, name="Saved view")
        return SaveVisualResultSpec(output_id=ref_id, title="Saved visual")

    if table is None:
        return PreviewTableSpec(table_name="unknown")

    if intent == AnalyticsIntent.visual_result:
        gb = _groupby_cols(table)
        metrics = _metric_cols(table)
        return GenerateVisualSpec(
            table_name=table.table_name,
            chart_type=_chart_type_from_question(question),
            x_column=gb[0] if gb else table.columns[0].column_name,
            y_column=metrics[0] if metrics else None,
        )

    if intent in (AnalyticsIntent.table_result, AnalyticsIntent.mixed_result):
        gb = _groupby_cols(table)
        metrics = _metric_cols(table)
        if gb and metrics:
            return AggregateTableSpec(
                table_name=table.table_name,
                group_by=gb[:2],
                metrics=[MetricSpec(column=metrics[0], aggregation=AllowedAggregation.sum)],
                sort_by=metrics[0],
                sort_desc=True,
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
            if gb and metric:
                return AggregateTableSpec(
                    table_name=table_name,
                    group_by=gb,
                    metrics=[MetricSpec(column=metric, aggregation=agg)],
                )
            return PreviewTableSpec(table_name=table_name)

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
                    result = run_preview_table(spec=spec, **common)
                    if plan.intent == AnalyticsIntent.text_answer:
                        return _table_to_text(result, version_id, title)
                    return result
                case "aggregate_table":
                    result = run_aggregate_table(spec=spec, **common)
                    if plan.intent == AnalyticsIntent.text_answer:
                        return _table_to_text(result, version_id, title)
                    return result
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
