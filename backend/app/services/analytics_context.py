"""M12B: Compact dataset context builder for the analytics planner.

Collects metadata for one DatasetVersion. Never dumps full row data.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.schemas.analytics_context import (
    _MAX_ARTIFACTS,
    _MAX_TOP_VALUES,
    DatasetContext,
    DatasetContextColumn,
    DatasetContextTable,
    DatasetContextView,
    DatasetContextVisual,
)


def build_dataset_context(
    *,
    dataset_id: UUID,
    dataset_version_id: UUID,
    dataset_repo: Any,
    version_repo: Any,
    table_repo: Any,
    profile_repo: Any,
    saved_view_repo: Any = None,
    saved_visual_repo: Any = None,
) -> DatasetContext | None:
    """Return compact context for one dataset version, or None if not found.

    All repos are protocol-compatible with both memory and DB implementations.
    """
    dataset = dataset_repo.get(dataset_id)
    if dataset is None:
        return None

    version = version_repo.get(dataset_version_id)
    if version is None:
        return None

    tables = table_repo.list_by_version(dataset_version_id)

    profiles_by_table: dict[str, Any] = {
        p.table_name: p
        for p in profile_repo.list_by_version(dataset_version_id)
    }

    context_tables: list[DatasetContextTable] = []
    for table in tables:
        profile = profiles_by_table.get(table.table_name)

        columns: list[DatasetContextColumn] = []
        quality_issue_count = 0

        if profile is not None:
            for cp in profile.column_profiles:
                columns.append(
                    DatasetContextColumn(
                        column_name=cp.column_name,
                        data_type=str(cp.data_type),
                        null_percent=cp.null_percent,
                        unique_count=cp.unique_count,
                        is_likely_id=cp.is_likely_id,
                        is_likely_metric=cp.is_likely_metric,
                        is_likely_categorical=cp.is_likely_categorical,
                        is_likely_date=cp.is_likely_date,
                        top_values=cp.top_values[:_MAX_TOP_VALUES],
                    )
                )
            quality_issue_count = len(profile.quality_issues)

        context_tables.append(
            DatasetContextTable(
                table_name=table.table_name,
                row_count=profile.row_count if profile is not None else table.row_count,
                column_count=profile.column_count if profile is not None else table.column_count,
                columns=columns,
                has_profile=profile is not None,
                quality_issue_count=quality_issue_count,
            )
        )

    saved_views: list[DatasetContextView] = []
    if saved_view_repo is not None:
        for sv in saved_view_repo.list_by_version(dataset_version_id)[:_MAX_ARTIFACTS]:
            saved_views.append(
                DatasetContextView(
                    saved_view_id=sv.saved_view_id,
                    name=sv.name,
                    source_type=str(sv.source_type),
                    row_count=sv.row_count,
                    column_count=sv.column_count,
                )
            )

    saved_visuals: list[DatasetContextVisual] = []
    if saved_visual_repo is not None:
        for sv in saved_visual_repo.list_by_version(dataset_version_id)[:_MAX_ARTIFACTS]:
            saved_visuals.append(
                DatasetContextVisual(
                    visual_id=sv.visual_id,
                    title=sv.title,
                    chart_type=sv.chart_type,
                )
            )

    return DatasetContext(
        dataset_id=dataset_id,
        dataset_name=dataset.name,
        dataset_version_id=dataset_version_id,
        version_number=version.version_number,
        version_type=str(version.version_type),
        display_name=version.display_name,
        tables=context_tables,
        saved_views=saved_views,
        saved_visuals=saved_visuals,
    )
