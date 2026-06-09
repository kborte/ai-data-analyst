"""Tests for M11D compatibility helpers in saved_artifacts service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.repositories.memory import (
    SavedViewRepository,
    SavedVisualRepository,
)
from app.schemas.saved_view import SavedViewSourceType
from app.schemas.saved_visual import SavedVisualSourceType
from app.schemas.common import ArtifactStatus
from app.schemas.visualization import (
    ChartExecutionResult,
    ChartSpec,
    ExecutionStatus,
    SeriesSpec,
    VisualizationResult,
)
from app.services.saved_artifacts import (
    save_view_from_storage_artifact,
    save_view_from_table_result,
    save_visual_from_chart_spec,
    save_visual_from_visualization_result,
)
from app.tools.files.storage_service import StoredFile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKSPACE_ID = uuid.uuid4()
DATASET_ID = uuid.uuid4()
VERSION_ID = uuid.uuid4()


def _fake_storage(path: str = "views/test.csv", backend: str = "local") -> MagicMock:
    storage = MagicMock()
    storage.save.return_value = StoredFile(
        storage_backend=backend,
        storage_path=path,
        storage_bucket=None,
        storage_format="csv",
    )
    return storage


def _chart_spec() -> ChartSpec:
    return ChartSpec(
        visualization_id=str(uuid.uuid4()),
        title="Revenue over time",
        chart_type="line",
        x_key="month",
        series=[SeriesSpec(data_key="revenue", label="Revenue")],
        data=[{"month": "Jan", "revenue": 100}],
        description="",
    )


def _viz_result(dataset_version_id: uuid.UUID) -> VisualizationResult:
    spec = _chart_spec()
    exec_result = ChartExecutionResult(
        visualization_id=uuid.UUID(spec.visualization_id),
        status=ExecutionStatus.success,
        chart_spec=spec,
    )
    return VisualizationResult(
        visualization_result_id=uuid.uuid4(),
        visualization_plan_id=uuid.uuid4(),
        dataset_version_id=dataset_version_id,
        status=ArtifactStatus.completed,
        chart_specs=[spec],
        chart_results=[exec_result],
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# save_view_from_table_result
# ---------------------------------------------------------------------------

class TestSaveViewFromTableResult:
    def test_returns_saved_view_with_correct_scope(self):
        repo = SavedViewRepository()
        storage = _fake_storage()

        view = save_view_from_table_result(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            name="Monthly Revenue",
            columns=["month", "revenue"],
            rows=[["Jan", 100], ["Feb", 200]],
            repo=repo,
            storage=storage,
        )

        assert view.workspace_id == WORKSPACE_ID
        assert view.dataset_id == DATASET_ID
        assert view.dataset_version_id == VERSION_ID
        assert view.name == "Monthly Revenue"
        assert view.row_count == 2
        assert view.column_count == 2
        assert view.storage_format == "csv"

    def test_uploads_csv_to_storage(self):
        repo = SavedViewRepository()
        storage = _fake_storage()

        save_view_from_table_result(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            name="Test",
            columns=["a", "b"],
            rows=[[1, 2]],
            repo=repo,
            storage=storage,
        )

        storage.save.assert_called_once()
        call_args = storage.save.call_args
        csv_bytes: bytes = call_args[0][1]
        assert b"a,b" in csv_bytes
        assert b"1,2" in csv_bytes

    def test_persisted_in_repo(self):
        repo = SavedViewRepository()
        storage = _fake_storage()

        view = save_view_from_table_result(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            name="Revenue Summary",
            columns=["x"],
            rows=[[1]],
            repo=repo,
            storage=storage,
        )

        assert repo.get(view.saved_view_id) is not None

    def test_version_scoping_preserved(self):
        """Saving with a different version id keeps that version reference."""
        repo = SavedViewRepository()
        storage = _fake_storage()
        v2 = uuid.uuid4()

        view = save_view_from_table_result(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=v2,
            name="V2 Summary",
            columns=["x"],
            rows=[[1]],
            repo=repo,
            storage=storage,
        )

        assert view.dataset_version_id == v2


# ---------------------------------------------------------------------------
# save_view_from_storage_artifact
# ---------------------------------------------------------------------------

class TestSaveViewFromStorageArtifact:
    def test_returns_saved_view_pointing_to_artifact(self):
        repo = SavedViewRepository()

        view = save_view_from_storage_artifact(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            name="Pre-generated export",
            storage_backend="supabase",
            storage_path="workspaces/x/datasets/y/views/z.parquet",
            storage_format="parquet",
            repo=repo,
            row_count=500,
            column_count=10,
        )

        assert view.storage_path == "workspaces/x/datasets/y/views/z.parquet"
        assert view.storage_format == "parquet"
        assert view.row_count == 500
        assert view.dataset_version_id == VERSION_ID
        assert view.source_type == SavedViewSourceType.manual

    def test_persisted_in_repo(self):
        repo = SavedViewRepository()

        view = save_view_from_storage_artifact(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            name="Artifact",
            storage_backend="local",
            storage_path="some/path.csv",
            storage_format="csv",
            repo=repo,
        )

        assert repo.get(view.saved_view_id) is not None


# ---------------------------------------------------------------------------
# save_visual_from_chart_spec
# ---------------------------------------------------------------------------

class TestSaveVisualFromChartSpec:
    def test_returns_saved_visual_with_correct_scope(self):
        repo = SavedVisualRepository()
        spec = _chart_spec()

        visual = save_visual_from_chart_spec(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            title="Revenue Over Time",
            chart_spec=spec,
            repo=repo,
        )

        assert visual.workspace_id == WORKSPACE_ID
        assert visual.dataset_id == DATASET_ID
        assert visual.dataset_version_id == VERSION_ID
        assert visual.title == "Revenue Over Time"
        assert visual.chart_type == "line"
        assert visual.source_type == SavedVisualSourceType.chart_spec

    def test_chart_spec_json_stored(self):
        repo = SavedVisualRepository()
        spec = _chart_spec()

        visual = save_visual_from_chart_spec(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            title="Test",
            chart_spec=spec,
            repo=repo,
        )

        assert visual.chart_spec_json["chart_type"] == "line"
        assert visual.chart_spec_json["title"] == "Revenue over time"

    def test_persisted_in_repo(self):
        repo = SavedVisualRepository()
        spec = _chart_spec()

        visual = save_visual_from_chart_spec(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            title="Test",
            chart_spec=spec,
            repo=repo,
        )

        assert repo.get(visual.visual_id) is not None


# ---------------------------------------------------------------------------
# save_visual_from_visualization_result
# ---------------------------------------------------------------------------

class TestSaveVisualFromVisualizationResult:
    def test_preserves_caller_version_id(self):
        """Version id must come from the caller, not from viz_result."""
        repo = SavedVisualRepository()
        result_version = uuid.uuid4()
        caller_version = uuid.uuid4()  # different from result_version
        viz = _viz_result(result_version)

        visual = save_visual_from_visualization_result(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=caller_version,
            title="Revenue Chart",
            viz_result=viz,
            repo=repo,
        )

        assert visual.dataset_version_id == caller_version

    def test_references_source_visualization_result(self):
        repo = SavedVisualRepository()
        viz = _viz_result(VERSION_ID)

        visual = save_visual_from_visualization_result(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            title="Revenue Chart",
            viz_result=viz,
            repo=repo,
        )

        assert visual.source_visualization_result_id == viz.visualization_result_id
        assert visual.source_type == SavedVisualSourceType.visualization_result

    def test_chart_spec_extracted_from_result(self):
        repo = SavedVisualRepository()
        viz = _viz_result(VERSION_ID)

        visual = save_visual_from_visualization_result(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            title="Revenue Chart",
            viz_result=viz,
            repo=repo,
        )

        assert visual.chart_type == "line"
        assert "chart_type" in visual.chart_spec_json

    def test_empty_chart_results_produces_unknown_type(self):
        repo = SavedVisualRepository()
        viz = _viz_result(VERSION_ID)
        viz = viz.model_copy(update={"chart_results": []})

        visual = save_visual_from_visualization_result(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            title="Empty",
            viz_result=viz,
            repo=repo,
        )

        assert visual.chart_type == "unknown"
        assert visual.chart_spec_json == {}

    def test_persisted_in_repo(self):
        repo = SavedVisualRepository()
        viz = _viz_result(VERSION_ID)

        visual = save_visual_from_visualization_result(
            workspace_id=WORKSPACE_ID,
            dataset_id=DATASET_ID,
            dataset_version_id=VERSION_ID,
            title="Test",
            viz_result=viz,
            repo=repo,
        )

        assert repo.get(visual.visual_id) is not None
