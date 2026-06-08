"""
Deterministic cleaning rule engine.

Converts DataProfile.quality_issues into a list of CleaningStep objects.
No LLM calls. No data mutation. No execution.
"""

import uuid
from uuid import UUID

from app.schemas.cleaning import (
    CleaningIssue,
    CleaningOperation,
    CleaningPreview,
    CleaningRecommendation,
    CleaningStep,
)
from app.schemas.common import CleaningOperationType, DefaultDecision, ImpactLevel, IssueType
from app.schemas.profile import DataProfile, DataQualityIssue

_NAMESPACE = uuid.NAMESPACE_DNS


def _step_uuid(seq: int, issue_type: str, table: str, column: str | None) -> UUID:
    """Stable, deterministic UUID derived from step identity."""
    name = f"clean_{seq:03d}_{issue_type}_{table}_{column or ''}"
    return uuid.uuid5(_NAMESPACE, name)


def _to_cleaning_issue(issue: DataQualityIssue) -> CleaningIssue:
    return CleaningIssue(
        issue_type=issue.issue_type,
        table_name=issue.table_name,
        column_name=issue.column_name,
        description=issue.description,
        affected_rows_count=issue.affected_rows_count,
        affected_rows_percent=issue.affected_rows_percent,
        sample_values=issue.sample_values,
    )


def _preview_no_row_change(row_count: int, col: str | None, metrics: list[str]) -> CleaningPreview:
    return CleaningPreview(
        rows_before=row_count,
        estimated_rows_after=row_count,
        estimated_rows_removed=0,
        columns_changed=[col] if col else [],
        metrics_potentially_affected=metrics,
    )


def _preview_row_removal(row_count: int, removed: int, col: str | None, metrics: list[str]) -> CleaningPreview:
    return CleaningPreview(
        rows_before=row_count,
        estimated_rows_after=max(row_count - removed, 0),
        estimated_rows_removed=removed,
        columns_changed=[col] if col else [],
        metrics_potentially_affected=metrics,
    )


def _handle_missing_values(
    issue: DataQualityIssue,
    seq: int,
    profile: DataProfile,
) -> CleaningStep:
    col = issue.column_name
    is_metric = col in profile.likely_metric_columns
    is_id = col in profile.likely_id_columns
    is_date = col in profile.likely_date_columns
    is_categorical = col in profile.likely_categorical_columns
    is_key = is_metric or is_id or is_date
    pct = issue.affected_rows_percent
    row_count = profile.row_count
    metrics = [col] if (is_metric and col) else []

    if is_key:
        return CleaningStep(
            step_id=_step_uuid(seq, "missing_values", issue.table_name, col),
            sequence_order=seq,
            issue=_to_cleaning_issue(issue),
            recommendation=CleaningRecommendation(
                action_type="drop_rows_with_missing_key_fields",
                recommended_action=f"Drop rows where '{col}' is missing",
                rationale=f"'{col}' is a key {'metric' if is_metric else 'id/date'} column; missing values would corrupt analysis.",
                impact_level=ImpactLevel.high,
                affects_key_metrics=is_metric,
                requires_human_approval=True,
                default_decision=DefaultDecision.require_review,
            ),
            operation=CleaningOperation(
                operation_type=CleaningOperationType.drop_rows,
                parameters={"strategy": "drop_rows_with_missing_key_fields", "column": col},
            ),
            preview=_preview_row_removal(row_count, issue.affected_rows_count, col, metrics),
        )

    if is_categorical:
        needs_approval = pct >= 10.0
        return CleaningStep(
            step_id=_step_uuid(seq, "missing_values", issue.table_name, col),
            sequence_order=seq,
            issue=_to_cleaning_issue(issue),
            recommendation=CleaningRecommendation(
                action_type="fill_missing_constant",
                recommended_action=f"Fill missing '{col}' values with 'Unknown'",
                rationale=f"'{col}' is categorical; filling with a sentinel preserves row count.",
                impact_level=ImpactLevel.medium if needs_approval else ImpactLevel.low,
                affects_key_metrics=False,
                requires_human_approval=needs_approval,
                default_decision=DefaultDecision.require_review if needs_approval else DefaultDecision.approve,
            ),
            operation=CleaningOperation(
                operation_type=CleaningOperationType.fill_missing,
                parameters={"strategy": "constant", "fill_value": "Unknown", "column": col},
            ),
            preview=_preview_no_row_change(row_count, col, []),
        )

    # Low-importance column
    return CleaningStep(
        step_id=_step_uuid(seq, "missing_values", issue.table_name, col),
        sequence_order=seq,
        issue=_to_cleaning_issue(issue),
        recommendation=CleaningRecommendation(
            action_type="ignore_issue",
            recommended_action=f"Ignore missing values in '{col}'",
            rationale=f"'{col}' is not a key column and missing rate is acceptable.",
            impact_level=ImpactLevel.low,
            affects_key_metrics=False,
            requires_human_approval=False,
            default_decision=DefaultDecision.approve,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.ignore_issue,
            parameters={"column": col},
        ),
        preview=_preview_no_row_change(row_count, col, []),
    )


def _handle_duplicate_rows(issue: DataQualityIssue, seq: int, profile: DataProfile) -> CleaningStep:
    row_count = profile.row_count
    return CleaningStep(
        step_id=_step_uuid(seq, "duplicate_rows", issue.table_name, None),
        sequence_order=seq,
        issue=_to_cleaning_issue(issue),
        recommendation=CleaningRecommendation(
            action_type="remove_exact_duplicates",
            recommended_action="Remove exact duplicate rows from the table",
            rationale="Duplicate rows inflate counts and distort aggregations.",
            impact_level=ImpactLevel.high,
            affects_key_metrics=True,
            requires_human_approval=True,
            default_decision=DefaultDecision.require_review,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.deduplicate,
            parameters={"strategy": "exact"},
        ),
        preview=_preview_row_removal(row_count, issue.affected_rows_count, None, []),
    )


def _handle_whitespace(issue: DataQualityIssue, seq: int, profile: DataProfile) -> CleaningStep:
    col = issue.column_name
    return CleaningStep(
        step_id=_step_uuid(seq, "whitespace", issue.table_name, col),
        sequence_order=seq,
        issue=_to_cleaning_issue(issue),
        recommendation=CleaningRecommendation(
            action_type="trim_whitespace",
            recommended_action=f"Trim leading/trailing whitespace in '{col}'",
            rationale="Whitespace causes false uniqueness and join mismatches.",
            impact_level=ImpactLevel.low,
            affects_key_metrics=False,
            requires_human_approval=False,
            default_decision=DefaultDecision.approve,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.strip_whitespace,
            parameters={"column": col},
        ),
        preview=_preview_no_row_change(profile.row_count, col, []),
    )


def _handle_numeric_as_text(issue: DataQualityIssue, seq: int, profile: DataProfile) -> CleaningStep:
    col = issue.column_name
    is_metric = col in profile.likely_metric_columns
    metrics = [col] if is_metric else []
    return CleaningStep(
        step_id=_step_uuid(seq, "numeric_stored_as_text", issue.table_name, col),
        sequence_order=seq,
        issue=_to_cleaning_issue(issue),
        recommendation=CleaningRecommendation(
            action_type="convert_numeric",
            recommended_action=f"Cast '{col}' from text to numeric",
            rationale=f"'{col}' contains numeric values stored as strings; casting enables aggregation.",
            impact_level=ImpactLevel.high if is_metric else ImpactLevel.medium,
            affects_key_metrics=is_metric,
            requires_human_approval=is_metric,
            default_decision=DefaultDecision.require_review if is_metric else DefaultDecision.approve,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.cast_type,
            parameters={"column": col, "target_type": "numeric"},
        ),
        preview=_preview_no_row_change(profile.row_count, col, metrics),
    )


def _handle_date_as_text(issue: DataQualityIssue, seq: int, profile: DataProfile) -> CleaningStep:
    col = issue.column_name
    is_date = col in profile.likely_date_columns
    needs_approval = is_date
    return CleaningStep(
        step_id=_step_uuid(seq, "date_stored_as_text", issue.table_name, col),
        sequence_order=seq,
        issue=_to_cleaning_issue(issue),
        recommendation=CleaningRecommendation(
            action_type="parse_dates",
            recommended_action=f"Parse '{col}' from text to date/datetime",
            rationale=f"'{col}' contains date-like strings; parsing enables time-series operations.",
            impact_level=ImpactLevel.medium,
            affects_key_metrics=False,
            requires_human_approval=needs_approval,
            default_decision=DefaultDecision.require_review if needs_approval else DefaultDecision.approve,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.parse_dates,
            parameters={"column": col},
        ),
        preview=_preview_no_row_change(profile.row_count, col, []),
    )


def _handle_high_cardinality(issue: DataQualityIssue, seq: int, profile: DataProfile) -> CleaningStep:
    col = issue.column_name
    return CleaningStep(
        step_id=_step_uuid(seq, "high_cardinality_category", issue.table_name, col),
        sequence_order=seq,
        issue=_to_cleaning_issue(issue),
        recommendation=CleaningRecommendation(
            action_type="ignore_issue",
            recommended_action=f"Accept high cardinality in '{col}'",
            rationale="High cardinality in a categorical column is informational only; no action required.",
            impact_level=ImpactLevel.low,
            affects_key_metrics=False,
            requires_human_approval=False,
            default_decision=DefaultDecision.approve,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.ignore_issue,
            parameters={"column": col},
        ),
        preview=_preview_no_row_change(profile.row_count, col, []),
    )


def _handle_mixed_types(issue: DataQualityIssue, seq: int, profile: DataProfile) -> CleaningStep:
    col = issue.column_name
    return CleaningStep(
        step_id=_step_uuid(seq, "mixed_types", issue.table_name, col),
        sequence_order=seq,
        issue=_to_cleaning_issue(issue),
        recommendation=CleaningRecommendation(
            action_type="ignore_issue",
            recommended_action=f"Flag '{col}' for manual review — contains mixed value types",
            rationale="Mixed types require human interpretation; auto-casting may lose data.",
            impact_level=ImpactLevel.medium,
            affects_key_metrics=False,
            requires_human_approval=True,
            default_decision=DefaultDecision.require_review,
        ),
        operation=CleaningOperation(
            operation_type=CleaningOperationType.ignore_issue,
            parameters={"column": col, "reason": "mixed_types"},
        ),
        preview=_preview_no_row_change(profile.row_count, col, []),
    )


_HANDLERS = {
    IssueType.missing_values: _handle_missing_values,
    IssueType.duplicate_rows: _handle_duplicate_rows,
    IssueType.whitespace: _handle_whitespace,
    IssueType.numeric_stored_as_text: _handle_numeric_as_text,
    IssueType.date_stored_as_text: _handle_date_as_text,
    IssueType.high_cardinality_category: _handle_high_cardinality,
    IssueType.mixed_types: _handle_mixed_types,
}


def generate_cleaning_steps(profile: DataProfile) -> list[CleaningStep]:
    """
    Convert DataProfile quality issues into a deterministic list of CleaningSteps.
    Unknown issue types are skipped.
    """
    steps: list[CleaningStep] = []
    seq = 1
    for issue in profile.quality_issues:
        handler = _HANDLERS.get(issue.issue_type)
        if handler is None:
            continue
        steps.append(handler(issue, seq, profile))
        seq += 1
    return steps
