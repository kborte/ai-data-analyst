"""Integration tests for profile API endpoints (M10D: job-based profiling)."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
from app.schemas.workspace import Workspace
from app.tools.files.storage_service import LocalStorageBackend
from app.worker.runner import run_one

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_FILE = FIXTURES / "simple_sales.csv"
WORKSPACE_ID = str(uuid4())


@pytest.fixture()
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture()
def ctx(storage_dir: Path):
    fresh = Repos()
    fresh.workspace.save(Workspace(
        workspace_id=UUID(WORKSPACE_ID),
        name="test workspace",
        created_by_user_id=uuid4(),
        created_at=datetime.now(tz=UTC),
    ))
    backend = LocalStorageBackend(str(storage_dir))
    app.dependency_overrides[get_repos] = lambda: fresh
    app.dependency_overrides[get_storage] = lambda: backend
    client = TestClient(app)
    yield client, fresh, backend
    app.dependency_overrides.clear()


@pytest.fixture()
def xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "January"
    ws1.append(["date", "product", "revenue"])
    ws1.append(["2024-01-01", "Widget A", 500])
    ws2 = wb.create_sheet("February")
    ws2.append(["date", "product", "revenue"])
    ws2.append(["2024-02-01", "Widget B", 250])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _do_upload_and_get_ids(client, repos, backend):
    """Upload CSV and run worker; return (dataset_id, version_id)."""
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    versions = list(repos.dataset_version._store.values())
    v = versions[0]
    return v.dataset_id, v.dataset_version_id


def _run_profile(client, repos, backend, dataset_id, version_id):
    """Create profile job, run worker, return profile list from repos."""
    resp = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile")
    assert resp.status_code == 201
    run_one(repos.job, repos, storage=backend, llm=None)
    return repos.profile.list_by_version(version_id)


# ---------------------------------------------------------------------------
# Profile route returns a queued job
# ---------------------------------------------------------------------------

def test_profile_route_returns_queued_job(ctx) -> None:
    client, repos, backend = ctx
    dataset_id, version_id = _do_upload_and_get_ids(client, repos, backend)
    resp = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile")
    assert resp.status_code == 201
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "queued"
    assert body["job_type"] == "profile_dataset"


def test_profile_unknown_version_404(ctx) -> None:
    client, repos, backend = ctx
    resp = client.post(f"/datasets/{uuid4()}/versions/{uuid4()}/profile")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Worker processes profile job end-to-end
# ---------------------------------------------------------------------------

def test_worker_completes_profile_job(ctx) -> None:
    client, repos, backend = ctx
    dataset_id, version_id = _do_upload_and_get_ids(client, repos, backend)
    resp = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile")
    job_id = resp.json()["job_id"]
    run_one(repos.job, repos, storage=backend, llm=None)
    from uuid import UUID
    job = repos.job.get(UUID(job_id))
    assert job.status == "completed"
    assert job.result_id is not None


def test_profile_csv_row_and_column_counts(ctx) -> None:
    client, repos, backend = ctx
    dataset_id, version_id = _do_upload_and_get_ids(client, repos, backend)
    profiles = _run_profile(client, repos, backend, dataset_id, version_id)
    assert len(profiles) == 1
    assert profiles[0].row_count == 5
    assert profiles[0].column_count == 4


def test_profile_csv_saved_in_repo_and_gettable(ctx) -> None:
    client, repos, backend = ctx
    dataset_id, version_id = _do_upload_and_get_ids(client, repos, backend)
    profiles = _run_profile(client, repos, backend, dataset_id, version_id)
    profile_id = profiles[0].profile_id
    resp = ctx[0].get(f"/profiles/{profile_id}")
    # Use client from ctx directly
    client2, _, _ = ctx
    resp = client2.get(f"/profiles/{profile_id}")
    assert resp.status_code == 200


def test_profile_csv_has_column_profiles(ctx) -> None:
    client, repos, backend = ctx
    dataset_id, version_id = _do_upload_and_get_ids(client, repos, backend)
    profiles = _run_profile(client, repos, backend, dataset_id, version_id)
    assert len(profiles[0].column_profiles) == 4


def test_profile_csv_revenue_is_metric(ctx) -> None:
    client, repos, backend = ctx
    dataset_id, version_id = _do_upload_and_get_ids(client, repos, backend)
    profiles = _run_profile(client, repos, backend, dataset_id, version_id)
    cols = {c.column_name: c for c in profiles[0].column_profiles}
    assert cols["revenue"].is_likely_metric


def test_profile_reads_from_duckdb_artifact(ctx, storage_dir: Path) -> None:
    client, repos, backend = ctx
    dataset_id, version_id = _do_upload_and_get_ids(client, repos, backend)
    version = repos.dataset_version.get(version_id)
    assert version.storage_path.endswith(".duckdb")
    assert (storage_dir / version.storage_path).exists()
    profiles = _run_profile(client, repos, backend, dataset_id, version_id)
    assert profiles[0].row_count == 5


# ---------------------------------------------------------------------------
# Excel multi-sheet profiling
# ---------------------------------------------------------------------------

def test_profile_excel_two_tables(ctx, xlsx_bytes: bytes) -> None:
    client, repos, backend = ctx
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    versions = list(repos.dataset_version._store.values())
    v = versions[0]
    profiles = _run_profile(client, repos, backend, v.dataset_id, v.dataset_version_id)
    assert len(profiles) == 2
    names = {p.table_name for p in profiles}
    assert "january" in names
    assert "february" in names


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_get_unknown_profile_404(ctx) -> None:
    client, repos, backend = ctx
    resp = client.get(f"/profiles/{uuid4()}")
    assert resp.status_code == 404
