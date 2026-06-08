"""
Route integration tests for upload endpoints.
Uses TestClient with dependency overrides and a tmp_path storage dir.
No external services, no real auth.
"""

import io
from pathlib import Path
from uuid import uuid4

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos
from app.main import app

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_FILE = FIXTURES / "simple_sales.csv"
TXT_FILE = FIXTURES / "company_context.txt"

WORKSPACE_ID = str(uuid4())


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("app.tools.files.storage.settings.LOCAL_STORAGE_DIR", str(tmp_path))
    fresh = Repos()
    app.dependency_overrides[get_repos] = lambda: fresh
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# CSV upload
# ---------------------------------------------------------------------------


def test_csv_upload_status_200(client: TestClient) -> None:
    data = CSV_FILE.read_bytes()
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", data, "text/csv")},
    )
    assert resp.status_code == 200


def test_csv_upload_creates_dataset(client: TestClient) -> None:
    data = CSV_FILE.read_bytes()
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", data, "text/csv")},
    ).json()
    assert body["dataset"]["name"] == "simple_sales"
    assert body["dataset"]["workspace_id"] == WORKSPACE_ID


def test_csv_upload_dataset_name_override(client: TestClient) -> None:
    data = CSV_FILE.read_bytes()
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", data, "text/csv")},
        data={"dataset_name": "My Custom Name"},
    ).json()
    assert body["dataset"]["name"] == "My Custom Name"


def test_csv_upload_version(client: TestClient) -> None:
    data = CSV_FILE.read_bytes()
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", data, "text/csv")},
    ).json()
    v = body["dataset_version"]
    assert v["version_number"] == 1
    assert v["version_type"] == "original"
    assert v["display_name"] == "Original upload"
    assert v["parent_version_id"] is None


def test_csv_upload_one_table(client: TestClient) -> None:
    data = CSV_FILE.read_bytes()
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", data, "text/csv")},
    ).json()
    assert len(body["dataset_tables"]) == 1
    assert len(body["previews"]) == 1


def test_csv_upload_preview_rows(client: TestClient) -> None:
    data = CSV_FILE.read_bytes()
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", data, "text/csv")},
    ).json()
    preview = body["previews"][0]
    assert preview["total_row_count"] == 5
    assert "date" in preview["columns"]
    assert len(preview["rows"]) == 5


def test_csv_upload_file_saved_to_disk(client: TestClient, tmp_path: Path) -> None:
    data = CSV_FILE.read_bytes()
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", data, "text/csv")},
    ).json()
    stored = body["uploaded_file"]["storage_path"]
    assert Path(stored).exists()


# ---------------------------------------------------------------------------
# Excel upload (multi-sheet fixture generated in-test)
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


def test_excel_upload_sheet_names(client: TestClient, xlsx_bytes: bytes) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    names = [t["table_name"] for t in body["dataset_tables"]]
    assert "January" in names
    assert "February" in names


def test_excel_upload_preview_row_counts(client: TestClient, xlsx_bytes: bytes) -> None:
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    by_name = {p["table_name"]: p for p in body["previews"]}
    assert by_name["January"]["total_row_count"] == 1
    assert by_name["February"]["total_row_count"] == 2


# ---------------------------------------------------------------------------
# Context document upload
# ---------------------------------------------------------------------------


def test_context_upload_status_200(client: TestClient) -> None:
    data = TXT_FILE.read_bytes()
    resp = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("company_context.txt", data, "text/plain")},
    )
    assert resp.status_code == 200


def test_context_upload_creates_document(client: TestClient) -> None:
    data = TXT_FILE.read_bytes()
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("company_context.txt", data, "text/plain")},
    ).json()
    assert body["context_document"]["workspace_id"] == WORKSPACE_ID
    assert "Acme" in body["preview"]
    assert body["char_count"] > 0


def test_context_upload_file_saved(client: TestClient, tmp_path: Path) -> None:
    data = TXT_FILE.read_bytes()
    body = client.post(
        f"/workspaces/{WORKSPACE_ID}/context-documents/upload",
        files={"file": ("company_context.txt", data, "text/plain")},
    ).json()
    assert Path(body["uploaded_file"]["storage_path"]).exists()


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
