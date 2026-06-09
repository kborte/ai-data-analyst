"""
Route integration tests for upload endpoints (M10D: job-based uploads).
Upload route creates a queued job; worker processes it end-to-end.
"""

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
from app.tools.files.storage_service import LocalStorageBackend
from app.worker.runner import run_one

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_FILE = FIXTURES / "simple_sales.csv"
TXT_FILE = FIXTURES / "company_context.txt"

WORKSPACE_ID = str(uuid4())


def _seed_workspace(repos: Repos, workspace_id: str) -> None:
    """Insert the workspace row required by the upload route's FK check."""
    from app.schemas.workspace import Workspace  # noqa: PLC0415
    ws = Workspace(
        workspace_id=UUID(workspace_id),
        name="Test Workspace",
        created_by_user_id=uuid4(),
        created_at=datetime.now(tz=UTC),
    )
    repos.workspace._store[ws.workspace_id] = ws


@pytest.fixture()
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture()
def ctx(storage_dir: Path):
    fresh_repos = Repos()
    _seed_workspace(fresh_repos, WORKSPACE_ID)
    backend = LocalStorageBackend(str(storage_dir))
    app.dependency_overrides[get_repos] = lambda: fresh_repos
    app.dependency_overrides[get_storage] = lambda: backend
    client = TestClient(app)
    yield client, fresh_repos, backend
    app.dependency_overrides.clear()


def _upload_csv(client: TestClient, repos: Repos, backend: LocalStorageBackend) -> dict:
    """Upload CSV, run worker, return first dataset_version from repos."""
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 201
    run_one(repos.job, repos, storage=backend, llm=None)
    versions = list(repos.dataset_version._store.values())
    assert versions
    return {"version": versions[-1], "job": resp.json()}


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
    ws2.append(["2024-02-02", "Widget C", 300])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Job response shape
# ---------------------------------------------------------------------------

def test_csv_upload_returns_queued_job(ctx) -> None:
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "queued"
    assert body["job_type"] == "upload_import"
    assert body["workspace_id"] == WORKSPACE_ID


def test_csv_upload_job_payload_contains_filename(ctx) -> None:
    client, repos, backend = ctx
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    ).json()
    assert body["payload_json"]["filename"] == "simple_sales.csv"


def test_csv_upload_pending_bytes_saved_to_storage(ctx, storage_dir: Path) -> None:
    client, repos, backend = ctx
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    ).json()
    pending_path = body["payload_json"]["pending_storage_path"]
    assert (storage_dir / pending_path).exists()


# ---------------------------------------------------------------------------
# Worker processes upload job end-to-end
# ---------------------------------------------------------------------------

def test_worker_completes_upload_job(ctx) -> None:
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    )
    job_id_str = resp.json()["job_id"]
    run_one(repos.job, repos, storage=backend, llm=None)
    from uuid import UUID
    job = repos.job.get(UUID(job_id_str))
    assert job.status == "completed"
    assert job.output_dataset_version_id is not None


def test_worker_creates_dataset(ctx) -> None:
    client, repos, backend = ctx
    _upload_csv(client, repos, backend)
    datasets = list(repos.dataset._store.values())
    assert len(datasets) == 1
    assert str(datasets[0].workspace_id) == WORKSPACE_ID


def test_worker_creates_version_with_duckdb_path(ctx) -> None:
    client, repos, backend = ctx
    result = _upload_csv(client, repos, backend)
    version = result["version"]
    assert version.storage_path is not None
    assert version.storage_path.endswith(".duckdb")


def test_worker_creates_version_number_1(ctx) -> None:
    client, repos, backend = ctx
    result = _upload_csv(client, repos, backend)
    assert result["version"].version_number == 1
    assert result["version"].version_type == "original"


def test_worker_saves_duckdb_artifact(ctx, storage_dir: Path) -> None:
    client, repos, backend = ctx
    result = _upload_csv(client, repos, backend)
    assert (storage_dir / result["version"].storage_path).exists()


def test_worker_saves_raw_upload(ctx, storage_dir: Path) -> None:
    client, repos, backend = ctx
    _upload_csv(client, repos, backend)
    uploaded_files = list(repos.uploaded_file._store.values())
    assert uploaded_files
    raw_path = uploaded_files[0].storage_path
    assert raw_path is not None
    assert (storage_dir / raw_path).exists()


def test_worker_table_has_no_individual_storage_path(ctx) -> None:
    client, repos, backend = ctx
    result = _upload_csv(client, repos, backend)
    tables = repos.dataset_table.list_by_version(result["version"].dataset_version_id)
    assert len(tables) == 1
    assert tables[0].storage_path is None


def test_worker_dataset_name_override(ctx) -> None:
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
        data={"dataset_name": "My Custom Name"},
    )
    assert resp.status_code == 201
    run_one(repos.job, repos, storage=backend, llm=None)
    datasets = list(repos.dataset._store.values())
    assert datasets[0].name == "My Custom Name"


# ---------------------------------------------------------------------------
# Excel upload
# ---------------------------------------------------------------------------

def test_excel_worker_creates_two_tables(ctx, xlsx_bytes: bytes) -> None:
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 201
    run_one(repos.job, repos, storage=backend, llm=None)
    versions = list(repos.dataset_version._store.values())
    tables = repos.dataset_table.list_by_version(versions[0].dataset_version_id)
    assert len(tables) == 2


def test_excel_worker_sheet_names_sanitized(ctx, xlsx_bytes: bytes) -> None:
    client, repos, backend = ctx
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    versions = list(repos.dataset_version._store.values())
    tables = repos.dataset_table.list_by_version(versions[0].dataset_version_id)
    names = {t.table_name for t in tables}
    assert "january" in names
    assert "february" in names


def test_excel_worker_duckdb_contains_both_tables(ctx, xlsx_bytes: bytes, storage_dir: Path) -> None:
    import duckdb

    client, repos, backend = ctx
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    versions = list(repos.dataset_version._store.values())
    db_path = storage_dir / versions[0].storage_path
    con = duckdb.connect(str(db_path), read_only=True)
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    con.close()
    assert sorted(tables) == ["february", "january"]


# ---------------------------------------------------------------------------
# Upload to existing dataset
# ---------------------------------------------------------------------------

def test_upload_to_existing_dataset_reuses_dataset(ctx) -> None:
    client, repos, backend = ctx
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    datasets = list(repos.dataset._store.values())
    dataset_id = str(datasets[0].dataset_id)

    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data2.csv", b"a,b\n3,4\n", "text/csv")},
        data={"dataset_id": dataset_id},
    )
    run_one(repos.job, repos, storage=backend, llm=None)

    datasets_after = list(repos.dataset._store.values())
    assert len(datasets_after) == 1


def test_upload_to_existing_dataset_increments_version(ctx) -> None:
    client, repos, backend = ctx
    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
    )
    run_one(repos.job, repos, storage=backend, llm=None)
    dataset_id = str(list(repos.dataset._store.values())[0].dataset_id)

    client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data2.csv", b"a,b\n3,4\n", "text/csv")},
        data={"dataset_id": dataset_id},
    )
    run_one(repos.job, repos, storage=backend, llm=None)

    versions = sorted(
        repos.dataset_version._store.values(), key=lambda v: v.version_number
    )
    assert versions[-1].version_number == 2


def test_upload_unknown_dataset_id_returns_404(ctx) -> None:
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data.csv", b"a\n1\n", "text/csv")},
        data={"dataset_id": str(uuid4())},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Context document upload (still synchronous)
# ---------------------------------------------------------------------------

def test_context_upload_status_200(ctx) -> None:
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("company_context.txt", TXT_FILE.read_bytes(), "text/plain")},
    )
    assert resp.status_code == 200


def test_context_upload_creates_document(ctx) -> None:
    client, repos, backend = ctx
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("company_context.txt", TXT_FILE.read_bytes(), "text/plain")},
    ).json()
    assert body["context_document"]["workspace_id"] == WORKSPACE_ID
    assert "Acme" in body["preview"]
    assert body["char_count"] > 0


def test_context_upload_file_saved_to_storage(ctx, storage_dir: Path) -> None:
    client, repos, backend = ctx
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("company_context.txt", TXT_FILE.read_bytes(), "text/plain")},
    ).json()
    raw_path = body["uploaded_file"]["storage_path"]
    assert (storage_dir / raw_path).exists()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_unsupported_tabular_extension(ctx) -> None:
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 422


def test_unsupported_context_extension(ctx) -> None:
    client, repos, backend = ctx
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("notes.docx", b"PK...", "application/octet-stream")},
    )
    assert resp.status_code == 422
