"""
Route integration tests for upload endpoints (M9C).
Uses TestClient with dependency overrides and a tmp_path LocalStorageBackend.
No external services.
"""

from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
from app.tools.files.storage_service import LocalStorageBackend

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_FILE = FIXTURES / "simple_sales.csv"
TXT_FILE = FIXTURES / "company_context.txt"

WORKSPACE_ID = str(uuid4())


@pytest.fixture()
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture()
def client(storage_dir: Path) -> TestClient:
    fresh_repos = Repos()
    backend = LocalStorageBackend(str(storage_dir))
    app.dependency_overrides[get_repos] = lambda: fresh_repos
    app.dependency_overrides[get_storage] = lambda: backend
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# CSV upload
# ---------------------------------------------------------------------------

def test_csv_upload_status_200(client: TestClient) -> None:
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 200


def test_csv_upload_creates_dataset(client: TestClient) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    ).json()
    assert body["dataset"]["name"] == "simple_sales"
    assert body["dataset"]["workspace_id"] == WORKSPACE_ID


def test_csv_upload_dataset_name_override(client: TestClient) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
        data={"dataset_name": "My Custom Name"},
    ).json()
    assert body["dataset"]["name"] == "My Custom Name"


def test_csv_upload_version(client: TestClient) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    ).json()
    v = body["dataset_version"]
    assert v["version_number"] == 1
    assert v["version_type"] == "original"
    assert v["display_name"] == "Original upload"
    assert v["parent_version_id"] is None


def test_csv_upload_version_has_duckdb_storage_path(client: TestClient) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    ).json()
    storage_path = body["dataset_version"]["storage_path"]
    assert storage_path is not None
    assert storage_path.endswith(".duckdb")


def test_csv_upload_raw_file_saved_to_storage(client: TestClient, storage_dir: Path) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    ).json()
    raw_path = body["uploaded_file"]["storage_path"]
    assert raw_path is not None
    # storage key is relative; LocalStorageBackend resolves under storage_dir
    assert (storage_dir / raw_path).exists()


def test_csv_upload_duckdb_artifact_saved_to_storage(client: TestClient, storage_dir: Path) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    ).json()
    ver_path = body["dataset_version"]["storage_path"]
    assert (storage_dir / ver_path).exists()


def test_csv_upload_one_table_no_storage_path(client: TestClient) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    ).json()
    assert len(body["dataset_tables"]) == 1
    # Table lives inside .duckdb — no individual storage_path
    assert body["dataset_tables"][0]["storage_path"] is None


def test_csv_upload_preview_rows(client: TestClient) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", CSV_FILE.read_bytes(), "text/csv")},
    ).json()
    preview = body["previews"][0]
    assert preview["total_row_count"] == 5
    assert "date" in preview["columns"]
    assert len(preview["rows"]) == 5


# ---------------------------------------------------------------------------
# Excel upload
# ---------------------------------------------------------------------------

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


def test_excel_upload_two_tables(client: TestClient, xlsx_bytes: bytes) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    assert len(body["dataset_tables"]) == 2
    assert len(body["previews"]) == 2


def test_excel_upload_sheet_names_sanitized(client: TestClient, xlsx_bytes: bytes) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    names = {t["table_name"] for t in body["dataset_tables"]}
    assert "january" in names
    assert "february" in names


def test_excel_upload_preview_row_counts(client: TestClient, xlsx_bytes: bytes) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    by_name = {p["table_name"]: p for p in body["previews"]}
    assert by_name["january"]["total_row_count"] == 1
    assert by_name["february"]["total_row_count"] == 2


def test_excel_upload_duckdb_contains_both_tables(client: TestClient, xlsx_bytes: bytes, storage_dir: Path) -> None:
    import duckdb

    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    db_path = storage_dir / body["dataset_version"]["storage_path"]
    con = duckdb.connect(str(db_path), read_only=True)
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    con.close()
    assert sorted(tables) == ["february", "january"]


# ---------------------------------------------------------------------------
# Upload to existing dataset (no new Dataset created)
# ---------------------------------------------------------------------------

def test_upload_to_existing_dataset_reuses_dataset(client: TestClient) -> None:
    csv = b"a,b\n1,2\n"
    first = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data.csv", csv, "text/csv")},
    ).json()
    dataset_id = first["dataset"]["dataset_id"]

    second = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data2.csv", csv, "text/csv")},
        data={"dataset_id": dataset_id},
    ).json()
    assert second["dataset"]["dataset_id"] == dataset_id


def test_upload_to_existing_dataset_increments_version(client: TestClient) -> None:
    csv = b"a,b\n1,2\n"
    first = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data.csv", csv, "text/csv")},
    ).json()
    dataset_id = first["dataset"]["dataset_id"]

    second = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data2.csv", csv, "text/csv")},
        data={"dataset_id": dataset_id},
    ).json()
    assert second["dataset_version"]["version_number"] == 2


def test_upload_unknown_dataset_id_returns_422(client: TestClient) -> None:
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data.csv", b"a\n1\n", "text/csv")},
        data={"dataset_id": str(uuid4())},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Context document upload
# ---------------------------------------------------------------------------

def test_context_upload_status_200(client: TestClient) -> None:
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("company_context.txt", TXT_FILE.read_bytes(), "text/plain")},
    )
    assert resp.status_code == 200


def test_context_upload_creates_document(client: TestClient) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("company_context.txt", TXT_FILE.read_bytes(), "text/plain")},
    ).json()
    assert body["context_document"]["workspace_id"] == WORKSPACE_ID
    assert "Acme" in body["preview"]
    assert body["char_count"] > 0


def test_context_upload_file_saved_to_storage(client: TestClient, storage_dir: Path) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("company_context.txt", TXT_FILE.read_bytes(), "text/plain")},
    ).json()
    raw_path = body["uploaded_file"]["storage_path"]
    assert (storage_dir / raw_path).exists()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_unsupported_tabular_extension(client: TestClient) -> None:
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("data.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 422


def test_unsupported_context_extension(client: TestClient) -> None:
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("notes.docx", b"PK...", "application/octet-stream")},
    )
    assert resp.status_code == 422


def test_empty_csv_file(client: TestClient) -> None:
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert resp.status_code == 422


def test_empty_context_file(client: TestClient) -> None:
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 422
