"""API tests for feature engineering routes (M6C)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos
from app.main import app
from app.schemas.common import ArtifactStatus, DatasetVersionType, DataType
from app.schemas.dataset import DatasetTable, DatasetVersion
from app.schemas.features import FeaturePlan, FeaturePlanJson
from app.schemas.profile import ColumnProfile, DataProfile

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
def ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.tools.files.storage.settings.LOCAL_STORAGE_DIR", str(tmp_path))
    fresh = Repos()
    app.dependency_overrides[get_repos] = lambda: fresh
    client = TestClient(app)
    yield client, fresh, tmp_path
    app.dependency_overrides.clear()


def _seed_version_with_csv(repos: Repos, tmp_path: Path) -> tuple[uuid.UUID, uuid.UUID]:
    version_id = uuid.uuid4()
    csv_path = tmp_path / "orders.csv"
    df = pd.DataFrame({"revenue": [100.0, 200.0], "order_count": [2.0, 4.0]})
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
        table_name="orders",
        storage_path=str(csv_path),
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
    client, repos, tmp_path = ctx
    version_id = _seed_version_with_csv(repos, tmp_path)
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
# 3. Execute route creates FeatureResult
# ---------------------------------------------------------------------------


def test_execute_creates_feature_result(ctx):
    client, repos, tmp_path = ctx
    version_id = _seed_version_with_csv(repos, tmp_path)
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
    assert "feature_result_id" in body
    assert body["status"] == "completed"


# ---------------------------------------------------------------------------
# 4. Execute route creates enriched DatasetVersion
# ---------------------------------------------------------------------------


def test_execute_creates_enriched_dataset_version(ctx):
    client, repos, tmp_path = ctx
    version_id = _seed_version_with_csv(repos, tmp_path)
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

    out_id = uuid.UUID(resp.json()["output_dataset_version_id"])
    out_version = repos.dataset_version.get(out_id)
    assert out_version is not None
    assert out_version.version_type == DatasetVersionType.enriched


# ---------------------------------------------------------------------------
# 5. Previous DatasetVersion is unchanged after execution
# ---------------------------------------------------------------------------


def test_execute_does_not_mutate_previous_version(ctx):
    client, repos, tmp_path = ctx
    version_id = _seed_version_with_csv(repos, tmp_path)
    csv_path = tmp_path / "orders.csv"
    original_bytes = csv_path.read_bytes()
    plan_id, feature_id = _seed_plan_with_aov(repos, version_id)

    client.post(
        f"/feature-plans/{plan_id}/execute",
        json={
            "workspace_id": str(uuid.uuid4()),
            "dataset_id": str(_DATASET_ID),
            "input_dataset_version_id": str(version_id),
            "executed_by_user_id": str(_USER_ID),
            "decisions": [{"feature_id": str(feature_id), "decision": "approve"}],
        },
    )

    assert csv_path.read_bytes() == original_bytes
    assert repos.dataset_version.get(version_id) is not None
