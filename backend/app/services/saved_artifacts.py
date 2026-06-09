"""Explicit save helpers for turning generated outputs into saved artifacts.

Saving is always caller-initiated — nothing here runs automatically.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.schemas.saved_view import SavedView, SavedViewSourceType
from app.schemas.saved_visual import SavedVisual, SavedVisualSourceType
from app.schemas.visualization import ChartSpec, VisualizationResult
from app.tools.files.storage_service import StorageBackend, saved_view_path


def save_view_from_table_result(
    *,
    workspace_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    name: str,
    columns: list[str],
    rows: list[list[Any]],
    repo: Any,
    storage: StorageBackend,
    description: str | None = None,
    source_spec_json: dict[str, Any] | None = None,
    created_by_user_id: UUID | None = None,
) -> SavedView:
    """Serialize table rows to CSV, upload to storage, and persist metadata."""
    view_id = uuid.uuid4()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    csv_bytes = buf.getvalue().encode()

    path = saved_view_path(workspace_id, dataset_id, view_id, "csv")
    stored = storage.save(path, csv_bytes)

    obj = SavedView(
        saved_view_id=view_id,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        name=name,
        description=description,
        source_type=SavedViewSourceType.query,
        source_spec_json=source_spec_json or {},
        storage_backend=stored.storage_backend,
        storage_bucket=stored.storage_bucket,
        storage_path=stored.storage_path,
        storage_format="csv",
        row_count=len(rows),
        column_count=len(columns),
        created_at=datetime.now(timezone.utc),
        created_by_user_id=created_by_user_id,
    )
    try:
        return repo.save(obj)
    except Exception:
        # Best-effort cleanup: storage artifact is not part of the Postgres transaction.
        # If the DB write fails, attempt to remove the orphaned artifact.
        # Cleanup failure must not hide the original DB error.
        try:
            storage.delete(path)
        except Exception:
            pass
        raise


def save_view_from_storage_artifact(
    *,
    workspace_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    name: str,
    storage_backend: str,
    storage_path: str,
    storage_format: str,
    repo: Any,
    storage_bucket: str | None = None,
    row_count: int | None = None,
    column_count: int | None = None,
    description: str | None = None,
    source_spec_json: dict[str, Any] | None = None,
    created_by_user_id: UUID | None = None,
) -> SavedView:
    """Point a SavedView at an artifact that already lives in storage."""
    obj = SavedView(
        saved_view_id=uuid.uuid4(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        name=name,
        description=description,
        source_type=SavedViewSourceType.manual,
        source_spec_json=source_spec_json or {},
        storage_backend=storage_backend,
        storage_bucket=storage_bucket,
        storage_path=storage_path,
        storage_format=storage_format,
        row_count=row_count,
        column_count=column_count,
        created_at=datetime.now(timezone.utc),
        created_by_user_id=created_by_user_id,
    )
    return repo.save(obj)


def save_visual_from_chart_spec(
    *,
    workspace_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    title: str,
    chart_spec: ChartSpec,
    repo: Any,
    description: str | None = None,
    source_spec_json: dict[str, Any] | None = None,
    created_by_user_id: UUID | None = None,
) -> SavedVisual:
    """Persist a SavedVisual from an in-memory ChartSpec."""
    obj = SavedVisual(
        visual_id=uuid.uuid4(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        title=title,
        description=description,
        chart_type=chart_spec.chart_type,
        chart_spec_json=chart_spec.model_dump(),
        source_type=SavedVisualSourceType.chart_spec,
        source_spec_json=source_spec_json or {},
        created_at=datetime.now(timezone.utc),
        created_by_user_id=created_by_user_id,
    )
    return repo.save(obj)


def save_visual_from_visualization_result(
    *,
    workspace_id: UUID,
    dataset_id: UUID,
    dataset_version_id: UUID,
    title: str,
    viz_result: VisualizationResult,
    repo: Any,
    chart_index: int = 0,
    description: str | None = None,
    created_by_user_id: UUID | None = None,
) -> SavedVisual:
    """Persist a SavedVisual from an existing VisualizationResult.

    dataset_version_id is taken from the caller, not inferred from viz_result,
    so that older-version results keep their original version reference.
    """
    chart_spec: ChartSpec | None = None
    if viz_result.chart_results and chart_index < len(viz_result.chart_results):
        chart_spec = viz_result.chart_results[chart_index].chart_spec

    chart_type = chart_spec.chart_type if chart_spec else "unknown"
    chart_spec_json = chart_spec.model_dump() if chart_spec else {}

    obj = SavedVisual(
        visual_id=uuid.uuid4(),
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        title=title,
        description=description,
        chart_type=chart_type,
        chart_spec_json=chart_spec_json,
        source_type=SavedVisualSourceType.visualization_result,
        source_visualization_result_id=viz_result.visualization_result_id,
        source_spec_json={},
        created_at=datetime.now(timezone.utc),
        created_by_user_id=created_by_user_id,
    )
    return repo.save(obj)
