"""M12A: Analytics planner schemas and plan contracts.

Simple specs (preview, aggregate, filter, join) use deterministic tools.
SqlQuerySpec lets the LLM emit a validated read-only SELECT for patterns
(top-N per group, window functions, CTEs, subqueries) that can't be
expressed with a flat AggregateTableSpec.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnalyticsIntent(StrEnum):
    text_answer = "text_answer"
    table_result = "table_result"
    visual_result = "visual_result"
    mixed_result = "mixed_result"
    save_table_result = "save_table_result"
    save_visual_result = "save_visual_result"
    unsupported = "unsupported"


class OutputType(StrEnum):
    text = "text"
    table = "table"
    visual = "visual"
    mixed = "mixed"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"


class AllowedAggregation(StrEnum):
    count = "count"
    sum = "sum"
    avg = "avg"
    min = "min"
    max = "max"
    median = "median"


class FilterOperator(StrEnum):
    eq = "eq"
    ne = "ne"
    gt = "gt"
    lt = "lt"
    gte = "gte"
    lte = "lte"
    in_ = "in"
    not_in = "not_in"
    is_null = "is_null"
    is_not_null = "is_not_null"
    contains = "contains"


# ---------------------------------------------------------------------------
# Sub-specs used inside tool specs
# ---------------------------------------------------------------------------

class MetricSpec(BaseModel):
    column: str
    aggregation: AllowedAggregation
    alias: str | None = None


class FilterSpec(BaseModel):
    column: str
    operator: FilterOperator
    value: Any | None = None


# ---------------------------------------------------------------------------
# Tool specs  (no sql / raw_sql field on any of these)
# ---------------------------------------------------------------------------

class PreviewTableSpec(BaseModel):
    tool_name: Literal["preview_table"] = "preview_table"
    table_name: str
    columns: list[str] = []
    limit: int = 100


class AggregateTableSpec(BaseModel):
    tool_name: Literal["aggregate_table"] = "aggregate_table"
    table_name: str
    group_by: list[str]
    metrics: list[MetricSpec]
    sort_by: str | None = None
    sort_desc: bool = True
    limit: int = 500
    # Optional: truncate date columns in group_by to this period before aggregating.
    # Values: "month", "year", "week", "quarter", "day"
    date_trunc_period: str | None = None


class FilterTableSpec(BaseModel):
    tool_name: Literal["filter_table"] = "filter_table"
    table_name: str
    filters: list[FilterSpec]
    columns: list[str] = []
    sort_by: str | None = None
    sort_desc: bool = False
    limit: int = 500


class SimpleJoinSpec(BaseModel):
    tool_name: Literal["simple_join"] = "simple_join"
    left_table: str
    right_table: str
    join_key_left: str
    join_key_right: str
    output_columns: list[str]
    limit: int = 500


class GenerateVisualSpec(BaseModel):
    tool_name: Literal["generate_visual"] = "generate_visual"
    table_name: str
    chart_type: str
    x_column: str
    y_column: str | None = None
    y_columns: list[str] = []
    group_by: str | None = None
    aggregation: AllowedAggregation | None = None


class SqlQuerySpec(BaseModel):
    """LLM-generated, validated read-only SELECT query.

    Used for patterns that can't be expressed with AggregateTableSpec:
    top-N per group, window functions, CTEs, multi-step subqueries.
    The query is validated (SELECT/WITH only, no DDL/DML) before execution.
    """
    tool_name: Literal["sql_query"] = "sql_query"
    sql: str
    table_name: str = ""  # primary table hint, used for title inference only


class SaveTableResultSpec(BaseModel):
    tool_name: Literal["save_table_result"] = "save_table_result"
    output_id: UUID
    name: str
    description: str | None = None


class SaveVisualResultSpec(BaseModel):
    tool_name: Literal["save_visual_result"] = "save_visual_result"
    output_id: UUID
    title: str
    description: str | None = None


ToolSpec = Annotated[
    Union[
        PreviewTableSpec,
        AggregateTableSpec,
        FilterTableSpec,
        SimpleJoinSpec,
        GenerateVisualSpec,
        SqlQuerySpec,
        SaveTableResultSpec,
        SaveVisualResultSpec,
    ],
    Field(discriminator="tool_name"),
]


# ---------------------------------------------------------------------------
# Prior output reference  (for follow-up questions and save requests)
# ---------------------------------------------------------------------------

class PriorOutputRef(BaseModel):
    output_id: UUID
    output_type: OutputType
    title: str | None = None
    dataset_version_id: UUID
    source_spec_json: dict[str, Any] = {}
    chart_spec_json: dict[str, Any] = {}
    storage_backend: str | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None


# ---------------------------------------------------------------------------
# Recent messages  (client-provided context; never persisted in M12)
# ---------------------------------------------------------------------------

class RecentMessage(BaseModel):
    role: MessageRole
    content: str
    output_refs: list[PriorOutputRef] = []


# ---------------------------------------------------------------------------
# Analytics request
# ---------------------------------------------------------------------------

class AnalyticsRequest(BaseModel):
    question: str
    dataset_id: UUID
    dataset_version_id: UUID
    recent_messages: list[RecentMessage] = []
    prior_output_refs: list[PriorOutputRef] = []


# ---------------------------------------------------------------------------
# Typed outputs  (all carry dataset_version_id)
# ---------------------------------------------------------------------------

class TextOutput(BaseModel):
    output_type: Literal["text"] = "text"
    dataset_version_id: UUID
    title: str
    content: str
    references: list[str] = []


class TableOutput(BaseModel):
    output_type: Literal["table"] = "table"
    dataset_version_id: UUID
    title: str
    description: str | None = None
    columns: list[str]
    preview_rows: list[list[Any]]
    row_count: int
    source_spec_json: dict[str, Any] = {}
    storage_backend: str | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    storage_format: str | None = None
    can_save_as_view: Literal[True] = True


class VisualOutput(BaseModel):
    output_type: Literal["visual"] = "visual"
    dataset_version_id: UUID
    title: str
    description: str | None = None
    chart_type: str
    chart_spec_json: dict[str, Any] = {}
    source_spec_json: dict[str, Any] = {}
    data_storage_backend: str | None = None
    data_storage_bucket: str | None = None
    data_storage_path: str | None = None
    can_save_to_visuals: Literal[True] = True


_MixedOutputItem = Annotated[
    Union[TextOutput, TableOutput, VisualOutput],
    Field(discriminator="output_type"),
]


class MixedOutput(BaseModel):
    output_type: Literal["mixed"] = "mixed"
    dataset_version_id: UUID
    title: str
    summary: str
    outputs: list[_MixedOutputItem] = []


AnalyticsOutput = Annotated[
    Union[TextOutput, TableOutput, VisualOutput, MixedOutput],
    Field(discriminator="output_type"),
]


# ---------------------------------------------------------------------------
# Analytics plan  (structured planner output; no raw SQL)
# ---------------------------------------------------------------------------

class AnalyticsPlan(BaseModel):
    intent: AnalyticsIntent
    question: str
    dataset_id: UUID
    dataset_version_id: UUID
    reasoning_summary: str
    tool_name: str
    tool_spec: ToolSpec
    expected_output_type: OutputType
    needs_storage: bool = False
    suggested_title: str
    suggested_description: str | None = None
    prior_output_ref: PriorOutputRef | None = None


# ---------------------------------------------------------------------------
# Analytics response
# ---------------------------------------------------------------------------

class AnalyticsResponse(BaseModel):
    dataset_id: UUID
    dataset_version_id: UUID
    question: str
    plan: AnalyticsPlan
    output: AnalyticsOutput


# ---------------------------------------------------------------------------
# Explicit save payloads  (M11 helpers must be called explicitly)
# ---------------------------------------------------------------------------

class SaveAsViewPayload(BaseModel):
    dataset_id: UUID
    dataset_version_id: UUID
    name: str
    description: str | None = None
    output_id: UUID
    storage_path: str | None = None
    storage_backend: str | None = None
    storage_format: str | None = None


class SaveAsVisualPayload(BaseModel):
    dataset_id: UUID
    dataset_version_id: UUID
    title: str
    description: str | None = None
    output_id: UUID
