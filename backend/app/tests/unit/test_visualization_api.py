"""API tests for visualization routes (M8C)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos
from app.main import app
from app.schemas.common import ArtifactStatus, ChartType, DatasetVersionType, DataType
from app.schemas.dataset import DatasetTable, DatasetVersion
from app.schemas.profile import ColumnProfile, DataProfile
from app.schemas.visualization import ChartSuggestion, VisualizationPlan, VisualizationPlanJson

_DATASET_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _col(
    name: str,
    dtype: DataType = DataType.float_,
    *,
    is_likely_date: bool = False,
    is_likely_metric: bool = False,
    unique_count: int = 100,
) -> ColumnProfile:
    return ColumnProfile(
        column_name=name,
        data_type=dtype,
        total_count=10,
        null_count=0,
        null_percent=0.0,
        unique_count=unique_count,
        unique_percent=float(unique_count),
        is_likely_date=is_likely_date,
        is_likely_metric=is_likely_metric,
    )


@pytest.fixture()
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fresh = Repos()
    app.dependency_overrides[get_repos] = lambda: fresh
    client = TestClient(app)
    yield client, fresh, tmp_path
    app.dependency_overrides.clear()


def _seed_version_with_csv(repos: Repos, tmp_path: Path) -> uuid.UUID:
    version_id = uuid.uuid4()
    csv_path = tmp_path / "sales.csv"
    df = pd.DataFrame({
        "order_date": ["2026-01-01", "2026-02-01", "2026-03-01"],
        "revenue": [100.0, 200.0, 150.0],
    })
    df.to_csv(csv_path, index=False)

    repos.dataset_version.save(DatasetVersion(
        dataset_version_id=version_id,
        dataset_id=_DATASET_ID,
        version_number=1,
        version_type=DatasetVersionType.original,
        created_by_user_id=_USER_ID,
        created_at=_now(),
    ))
    repos.dataset_table.save(DatasetTable(
        table_id=uuid.uuid4(),
        dataset_version_id=version_id,
        table_name="sales",
        storage_path=str(csv_path),
    ))
    return version_id


def _seed_visualization_plan(
    repos: Repos, version_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    viz_id = uuid.uuid4()
    suggestion = ChartSuggestion(
        visualization_id=viz_id,
        title="Revenue over time",
        description="How revenue changes over order_date.",
        chart_type=ChartType.line,
        input_table="sales",
        x_column="order_date",
        y_column="revenue",
        aggregation="sum",
        sort="asc",
        user_facing_explanation="Shows revenue trend over time.",
        requires_human_approval=True,
    )
    plan = VisualizationPlan(
        visualization_plan_id=uuid.uuid4(),
        dataset_version_id=version_id,
        status=ArtifactStatus.completed,
        plan_json=VisualizationPlanJson(suggestions=[suggestion]),
        created_at=_now(),
    )
    repos.visualization_plan.save(plan)
    return plan.visualization_plan_id, viz_id


# ---------------------------------------------------------------------------
# 1. Create visualization plan route works
# ---------------------------------------------------------------------------


def test_create_visualization_plan_route(ctx) -> None:
    client, repos, _ = ctx
    version_id = uuid.uuid4()
    profile = DataProfile(
        profile_id=uuid.uuid4(),
        dataset_version_id=version_id,
        table_name="sales",
        row_count=10,
        column_count=2,
        column_profiles=[
            _col("order_date", DataType.date, is_likely_date=True, unique_count=10),
            _col("revenue", DataType.float_, is_likely_metric=True, unique_count=10),
        ],
        created_at=_now(),
    )
    repos.profile.save(profile)

    resp = client.post(
        f"/datasets/{_DATASET_ID}/versions/{version_id}/visualization-plans",
        json={"profile_id": str(profile.profile_id)},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "visualization_plan_id" in body
    assert body["status"] == "completed"
    assert len(body["plan_json"]["suggestions"]) >= 1


# ---------------------------------------------------------------------------
# 2. Decision validation blocks missing approval
# ---------------------------------------------------------------------------


def test_validate_blocks_missing_approval(ctx) -> None:
    client, repos, tmp_path = ctx
    version_id = _seed_version_with_csv(repos, tmp_path)
    plan_id, _ = _seed_visualization_plan(repos, version_id)

    resp = client.post(
        f"/visualization-plans/{plan_id}/decisions/validate",
        json={"decisions": []},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["can_generate"] is False
    assert body["blocked_charts"] == 1


# ---------------------------------------------------------------------------
# 3. Generate route creates VisualizationResult with chart specs
# ---------------------------------------------------------------------------


def test_generate_creates_visualization_result(ctx) -> None:
    client, repos, tmp_path = ctx
    version_id = _seed_version_with_csv(repos, tmp_path)
    plan_id, viz_id = _seed_visualization_plan(repos, version_id)

    resp = client.post(
        f"/visualization-plans/{plan_id}/generate",
        json={
            "generated_by_user_id": str(_USER_ID),
            "decisions": [{"visualization_id": str(viz_id), "decision": "approve"}],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "visualization_result_id" in body
    assert body["status"] == "completed"
    assert len(body["chart_specs"]) == 1
    assert body["chart_specs"][0]["chart_type"] == "line"


# ---------------------------------------------------------------------------
# 4. Generate skips rejected charts
# ---------------------------------------------------------------------------


def test_generate_skips_rejected_charts(ctx) -> None:
    client, repos, tmp_path = ctx
    version_id = _seed_version_with_csv(repos, tmp_path)
    plan_id, viz_id = _seed_visualization_plan(repos, version_id)

    resp = client.post(
        f"/visualization-plans/{plan_id}/generate",
        json={
            "generated_by_user_id": str(_USER_ID),
            "decisions": [{"visualization_id": str(viz_id), "decision": "reject"}],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "completed"
    assert body["chart_specs"] == []


# ---------------------------------------------------------------------------
# 5. Generate does not create a new DatasetVersion
# ---------------------------------------------------------------------------


def test_generate_does_not_create_new_dataset_version(ctx) -> None:
    client, repos, tmp_path = ctx
    version_id = _seed_version_with_csv(repos, tmp_path)
    plan_id, viz_id = _seed_visualization_plan(repos, version_id)
    versions_before = len(repos.dataset_version._store)

    client.post(
        f"/visualization-plans/{plan_id}/generate",
        json={
            "generated_by_user_id": str(_USER_ID),
            "decisions": [{"visualization_id": str(viz_id), "decision": "approve"}],
        },
    )

    assert len(repos.dataset_version._store) == versions_before
    assert repos.dataset_version.get(version_id) is not None
