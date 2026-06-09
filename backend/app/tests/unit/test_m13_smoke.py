"""M13B: Smoke tests verifying key MVP flows still work after M13A hardening.

These are thin happy-path checks — not exhaustive feature tests. They confirm
that the commit/flush/rollback changes in M13A did not break existing flows.
Each flow has dedicated unit tests elsewhere; these just confirm integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_llm_provider, get_repos, get_storage
from app.main import app
from app.schemas.common import DatasetVersionType
from app.schemas.dataset import Dataset, DatasetVersion
from app.schemas.saved_view import SavedViewSourceType
from app.tools.data.duckdb_service import create_version_duckdb
from app.tools.files.storage_service import LocalStorageBackend
from app.tools.llm.provider import FakeLLMProvider
from app.worker.runner import run_one

import pandas as pd

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_FILE = FIXTURES / "simple_sales.csv"
WORKSPACE_ID = str(uuid4())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture()
def ctx(storage_dir: Path):
    """Standard memory-repos + local-storage client used across smoke tests."""
    repos = Repos()
    backend = LocalStorageBackend(str(storage_dir))
    app.dependency_overrides[get_repos] = lambda: repos
    app.dependency_overrides[get_storage] = lambda: backend
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    client = TestClient(app)
    yield client, repos, backend
    app.dependency_overrides.clear()


def _upload_and_run(client, repos, backend) -> DatasetVersion:
    """Upload CSV, run worker, return the created DatasetVersion."""
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 201
    run_one(repos.job, repos, storage=backend, llm=None)
    versions = list(repos.dataset_version._store.values())
    assert versions
    return versions[-1]


def _now():
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# 1. Upload smoke test
# ---------------------------------------------------------------------------

def test_upload_creates_dataset_version(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    assert version.storage_path is not None
    assert version.storage_path.endswith(".duckdb")
    assert version.version_number == 1
    assert version.version_type == DatasetVersionType.original


def test_upload_creates_dataset_tables(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    tables = repos.dataset_table.list_by_version(version.dataset_version_id)
    assert len(tables) >= 1


def test_upload_persists_duckdb_artifact(ctx, storage_dir: Path):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    assert version.storage_path is not None
    artifact = storage_dir / version.storage_path
    assert artifact.exists()


# ---------------------------------------------------------------------------
# 2. Profiling smoke test
# ---------------------------------------------------------------------------

def test_profile_job_completes(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    resp = client.post(
        f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/profile"
    )
    assert resp.status_code == 201
    run_one(repos.job, repos, storage=backend, llm=None)

    profiles = repos.profile.list_by_version(version.dataset_version_id)
    assert len(profiles) >= 1


def test_profile_has_column_profiles(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    client.post(
        f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/profile"
    )
    run_one(repos.job, repos, storage=backend, llm=None)

    profiles = repos.profile.list_by_version(version.dataset_version_id)
    assert profiles[0].column_profiles


# ---------------------------------------------------------------------------
# 3. Saved view creation smoke test
# ---------------------------------------------------------------------------

def test_saved_view_created_via_api(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    resp = client.post(
        f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/views",
        json={
            "name": "Revenue Table",
            "source_type": "query",
            "columns": ["date", "revenue"],
            "rows": [["2024-01-01", 500.0]],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Revenue Table"
    assert body["dataset_version_id"] == str(version.dataset_version_id)


def test_save_as_view_csv_artifact_written(ctx, storage_dir: Path):
    """Analytics save-as-view route uploads CSV via save_view_from_table_result."""
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    resp = client.post(
        "/analytics/table-results/save-as-view",
        json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "name": "Artifact View",
            "columns": ["x", "y"],
            "rows": [[1, 2], [3, 4]],
        },
    )
    assert resp.status_code == 201
    storage_path = resp.json().get("storage_path")
    assert storage_path is not None
    assert (storage_dir / storage_path).exists()


# ---------------------------------------------------------------------------
# 4. Saved visual creation smoke test
# ---------------------------------------------------------------------------

def test_saved_visual_created_via_api(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    resp = client.post(
        f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/visuals",
        json={
            "title": "Revenue Chart",
            "source_type": "direct",
            "chart_type": "bar",
            "chart_spec_json": {
                "visualization_id": str(uuid4()),
                "title": "Revenue Chart",
                "chart_type": "bar",
                "x_key": "date",
                "series": [{"data_key": "revenue", "label": "Revenue"}],
                "data": [],
                "description": "",
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Revenue Chart"
    assert body["dataset_version_id"] == str(version.dataset_version_id)


# ---------------------------------------------------------------------------
# 5. Analytics ask + explicit save smoke test
# ---------------------------------------------------------------------------

def test_analytics_ask_returns_output(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    resp = client.post(
        f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
        json={"question": "show the data"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["output"]["dataset_version_id"] == str(version.dataset_version_id)


def test_analytics_ask_does_not_auto_save(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    client.post(
        f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
        json={"question": "show the data"},
    )
    assert repos.saved_view.list_by_version(version.dataset_version_id) == []
    assert repos.saved_visual.list_by_version(version.dataset_version_id) == []


def test_analytics_save_as_view_via_route(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    resp = client.post(
        "/analytics/table-results/save-as-view",
        json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "name": "Smoke View",
            "columns": ["date", "revenue"],
            "rows": [["2024-01-01", 500.0]],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Smoke View"


def test_analytics_save_as_visual_via_route(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    resp = client.post(
        "/analytics/visual-results/save-as-visual",
        json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "title": "Smoke Chart",
            "chart_type": "bar",
            "chart_spec_json": {},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["title"] == "Smoke Chart"


# ---------------------------------------------------------------------------
# 6. Cleaning smoke test
# ---------------------------------------------------------------------------

def test_cleaning_plan_route_returns_201(ctx):
    client, repos, backend = ctx
    version = _upload_and_run(client, repos, backend)
    dataset = list(repos.dataset._store.values())[0]

    # Profile first so the cleaning planner has column metadata
    client.post(
        f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/profile"
    )
    run_one(repos.job, repos, storage=backend, llm=None)

    profiles = repos.profile.list_by_version(version.dataset_version_id)
    assert profiles, "profile must exist before creating cleaning plan"

    resp = client.post(
        f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/cleaning-plans",
        json={"profile_id": str(profiles[0].profile_id)},
    )
    assert resp.status_code == 201
