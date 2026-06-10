"""API tests for feature engineering routes (M9+: DuckDB-based)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
from app.tools.data.duckdb_service import create_version_duckdb, temp_duckdb_path
from app.tools.files.storage_service import LocalStorageBackend, version_path
from app.schemas.common import ArtifactStatus, DatasetVersionType, DataType
from app.schemas.dataset import DatasetTable, DatasetVersion
from app.schemas.features import FeaturePlan, FeaturePlanJson
from app.schemas.profile import ColumnProfile, DataProfile

_WORKSPACE_ID = uuid.uuid4()
_DATASET_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _col(name: str, dtype: DataType = DataType.float_, *, is_likely_date: bool = False) -> ColumnProfile:
    return ColumnProfile(
        column_name=name,
        data_type=dtype,
        total_count=10,
        null_count=0,
        null_percent=0.0,
        unique_count=10,
        unique_percent=100.0,
        is_likely_date=is_likely_date,
    )


@pytest.fixture()
def ctx(tmp_path: Path):
    fresh = Repos()
    backend = LocalStorageBackend(str(tmp_path / "storage"))
    app.dependency_overrides[get_repos] = lambda: fresh
    app.dependency_overrides[get_storage] = lambda: backend
    client = TestClient(app)
    yield client, fresh, backend
    app.dependency_overrides.clear()


def _seed_version_with_duckdb(repos: Repos, storage: LocalStorageBackend) -> uuid.UUID:
    version_id = uuid.uuid4()
    df = pd.DataFrame({"revenue": [100.0, 200.0], "order_count": [2.0, 4.0]})
    spath = version_path(_WORKSPACE_ID, _DATASET_ID, 1, "original")
    with temp_duckdb_path() as tmp_db:
        create_version_duckdb({"orders": df}, tmp_db)
        storage.save(spath, tmp_db.read_bytes())

    repos.dataset_version.save(DatasetVersion(
        dataset_version_id=version_id,
        dataset_id=_DATASET_ID,
        version_number=1,
        version_type=DatasetVersionType.original,
        storage_path=spath,
        created_by_user_id=_USER_ID,
        created_at=_now(),
    ))
    repos.dataset_table.save(DatasetTable(
        table_id=uuid.uuid4(),
        dataset_version_id=version_id,
        table_name="orders",
    ))
    return version_id


def _seed_plan_with_aov(repos: Repos, version_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    from app.schemas.common import FeatureOperationType
    from app.schemas.features import FeatureDefinition

    feature_id = uuid.uuid4()
    feature = FeatureDefinition(
        feature_id=feature_id,
        feature_name="aov",
        display_name="AOV",
        operation_type=FeatureOperationType.ratio,
        formula_display="revenue / order_count",
        input_table="orders",
        output_column="aov",
        required_columns=["revenue", "order_count"],
        parameters={"numerator": "revenue", "denominator": "order_count"},
        requires_human_approval=True,
    )
    plan = FeaturePlan(
        feature_plan_id=uuid.uuid4(),
        dataset_version_id=version_id,
        status=ArtifactStatus.completed,
        plan_json=FeaturePlanJson(features=[feature]),
        created_at=_now(),
    )
    repos.feature_plan.save(plan)
    return plan.feature_plan_id, feature_id


# ---------------------------------------------------------------------------
# 1. Feature plan route works
# ---------------------------------------------------------------------------


def test_feature_plan_route_creates_plan(ctx):
    client, repos, _ = ctx
    version_id = uuid.uuid4()
    profile = DataProfile(
        profile_id=uuid.uuid4(),
        dataset_version_id=version_id,
        table_name="orders",
        row_count=10,
        column_count=2,
        column_profiles=[
            _col("revenue"),
            _col("order_count"),
        ],
        created_at=_now(),
    )
    repos.profile.save(profile)

    resp = client.post(
        f"/datasets/{_DATASET_ID}/versions/{version_id}/feature-plans",
        json={"profile_id": str(profile.profile_id)},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "feature_plan_id" in body
    assert body["status"] == "completed"


# ---------------------------------------------------------------------------
# 2. Decision validation blocks missing approval
# ---------------------------------------------------------------------------


def test_validate_blocks_missing_approval(ctx):
    client, repos, backend = ctx
    version_id = _seed_version_with_duckdb(repos, backend)
    plan_id, _ = _seed_plan_with_aov(repos, version_id)

    resp = client.post(
        f"/feature-plans/{plan_id}/decisions/validate",
        json={"decisions": []},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["can_execute"] is False
    assert body["blocked_features"] == 1


# ---------------------------------------------------------------------------
# 3. Execute route creates queued job
# ---------------------------------------------------------------------------


def test_execute_creates_queued_job(ctx):
    client, repos, backend = ctx
    version_id = _seed_version_with_duckdb(repos, backend)
    plan_id, feature_id = _seed_plan_with_aov(repos, version_id)

    resp = client.post(
        f"/feature-plans/{plan_id}/execute",
        json={
            "workspace_id": str(uuid.uuid4()),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"feature_id": str(feature_id), "decision": "approve"}],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "queued"
    assert body["job_type"] == "execute_features"


# ---------------------------------------------------------------------------
# 4. Worker creates FeatureResult and enriched DatasetVersion
# ---------------------------------------------------------------------------


def test_worker_creates_feature_result_and_version(ctx):
    from app.worker.runner import run_one

    client, repos, backend = ctx
    version_id = _seed_version_with_duckdb(repos, backend)
    plan_id, feature_id = _seed_plan_with_aov(repos, version_id)

    resp = client.post(
        f"/feature-plans/{plan_id}/execute",
        json={
            "workspace_id": str(uuid.uuid4()),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"feature_id": str(feature_id), "decision": "approve"}],
        },
    )
    job_id = uuid.UUID(resp.json()["job_id"])
    run_one(repos.job, repos, storage=backend, llm=None)

    job = repos.job.get(job_id)
    assert job.status == "completed"
    assert job.result_type == "feature_result"
    assert job.result_id is not None
    assert job.output_dataset_version_id is not None

    out_version = repos.dataset_version.get(job.output_dataset_version_id)
    assert out_version is not None
    assert out_version.version_type == DatasetVersionType.enriched


# ---------------------------------------------------------------------------
# 5. Previous DatasetVersion is unchanged after execution
# ---------------------------------------------------------------------------


def test_execute_does_not_mutate_previous_version(ctx):
    from app.worker.runner import run_one

    client, repos, backend = ctx
    version_id = _seed_version_with_duckdb(repos, backend)
    original_storage_path = repos.dataset_version.get(version_id).storage_path
    original_bytes = backend.read(original_storage_path)
    plan_id, feature_id = _seed_plan_with_aov(repos, version_id)

    resp = client.post(
        f"/feature-plans/{plan_id}/execute",
        json={
            "workspace_id": str(uuid.uuid4()),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"feature_id": str(feature_id), "decision": "approve"}],
        },
    )
    run_one(repos.job, repos, storage=backend, llm=None)

    # Original artifact must not be overwritten.
    assert backend.read(original_storage_path) == original_bytes
    assert repos.dataset_version.get(version_id) is not None
