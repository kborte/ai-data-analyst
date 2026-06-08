"""API tests for cleaning plan endpoints (M4C)."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos
from app.main import app
from app.schemas.common import ImpactLevel, IssueType
from app.schemas.profile import DataProfile, DataQualityIssue

_DATASET_ID = uuid.uuid4()
_VERSION_ID = uuid.uuid4()


def _make_profile(issues: list[DataQualityIssue]) -> DataProfile:
    return DataProfile(
        profile_id=uuid.uuid4(),
        dataset_version_id=_VERSION_ID,
        table_name="orders",
        row_count=100,
        column_count=max(len({i.column_name for i in issues if i.column_name}), 1),
        column_profiles=[],
        quality_issues=issues,
        created_at=datetime.now(tz=UTC),
    )


def _whitespace_issue() -> DataQualityIssue:
    return DataQualityIssue(
        issue_type=IssueType.whitespace,
        table_name="orders",
        column_name="country",
        description="whitespace in country",
        affected_rows_count=3,
        affected_rows_percent=3.0,
        impact_level=ImpactLevel.low,
    )


@pytest.fixture()
def client_repos() -> tuple[TestClient, Repos]:
    fresh = Repos()
    app.dependency_overrides[get_repos] = lambda: fresh
    client = TestClient(app)
    yield client, fresh
    app.dependency_overrides.clear()


def _post_plan(client: TestClient, profile_id: uuid.UUID) -> dict:
    return client.post(
        f"/datasets/{_DATASET_ID}/versions/{_VERSION_ID}/cleaning-plans",
        json={"profile_id": str(profile_id)},
    )


# ---------------------------------------------------------------------------
# 1. POST creates and returns a cleaning plan
# ---------------------------------------------------------------------------


def test_post_creates_plan(client_repos: tuple) -> None:
    client, repos = client_repos
    profile = _make_profile([_whitespace_issue()])
    repos.profile.save(profile)

    resp = _post_plan(client, profile.profile_id)

    assert resp.status_code == 201
    body = resp.json()
    assert "cleaning_plan_id" in body
    assert body["dataset_version_id"] == str(_VERSION_ID)


# ---------------------------------------------------------------------------
# 2. Returned plan contains expected steps
# ---------------------------------------------------------------------------


def test_returned_plan_contains_steps(client_repos: tuple) -> None:
    client, repos = client_repos
    profile = _make_profile([_whitespace_issue()])
    repos.profile.save(profile)

    body = _post_plan(client, profile.profile_id).json()

    steps = body["plan_json"]["steps"]
    assert len(steps) == 1
    assert steps[0]["issue"]["issue_type"] == "whitespace"
    assert steps[0]["recommendation"]["requires_human_approval"] is False


# ---------------------------------------------------------------------------
# 3. Missing profile returns 404
# ---------------------------------------------------------------------------


def test_missing_profile_returns_404(client_repos: tuple) -> None:
    client, _ = client_repos
    resp = _post_plan(client, uuid.uuid4())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Route does not execute cleaning (no dataset mutation)
# ---------------------------------------------------------------------------


def test_route_does_not_mutate_dataset(client_repos: tuple) -> None:
    client, repos = client_repos
    profile = _make_profile([_whitespace_issue()])
    repos.profile.save(profile)

    _post_plan(client, profile.profile_id)

    # No new dataset versions created
    assert repos.dataset_version.list_by_dataset(_DATASET_ID) == []


# ---------------------------------------------------------------------------
# GET /cleaning-plans/{id}
# ---------------------------------------------------------------------------


def test_get_cleaning_plan(client_repos: tuple) -> None:
    client, repos = client_repos
    profile = _make_profile([_whitespace_issue()])
    repos.profile.save(profile)

    plan_id = _post_plan(client, profile.profile_id).json()["cleaning_plan_id"]

    resp = client.get(f"/cleaning-plans/{plan_id}")
    assert resp.status_code == 200
    assert resp.json()["cleaning_plan_id"] == plan_id


def test_get_missing_plan_returns_404(client_repos: tuple) -> None:
    client, _ = client_repos
    resp = client.get(f"/cleaning-plans/{uuid.uuid4()}")
    assert resp.status_code == 404
