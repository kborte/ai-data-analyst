"""Integration tests for profile API endpoints via TestClient."""

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
WORKSPACE_ID = str(uuid4())


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("app.tools.files.storage.settings.LOCAL_STORAGE_DIR", str(tmp_path))
    fresh = Repos()
    app.dependency_overrides[get_repos] = lambda: fresh
    yield TestClient(app)
    app.dependency_overrides.clear()


def _upload_csv(client: TestClient) -> dict:
    data = CSV_FILE.read_bytes()
    return client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("simple_sales.csv", data, "text/csv")},
    ).json()


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


# ---------------------------------------------------------------------------
# CSV profiling via API
# ---------------------------------------------------------------------------


def test_profile_csv_status_200(client: TestClient) -> None:
    upload = _upload_csv(client)
    dataset_id = upload["dataset"]["dataset_id"]
    version_id = upload["dataset_version"]["dataset_version_id"]
    resp = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile")
    assert resp.status_code == 200


def test_profile_csv_returns_list(client: TestClient) -> None:
    upload = _upload_csv(client)
    dataset_id = upload["dataset"]["dataset_id"]
    version_id = upload["dataset_version"]["dataset_version_id"]
    profiles = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile").json()
    assert isinstance(profiles, list)
    assert len(profiles) == 1


def test_profile_csv_row_and_column_counts(client: TestClient) -> None:
    upload = _upload_csv(client)
    dataset_id = upload["dataset"]["dataset_id"]
    version_id = upload["dataset_version"]["dataset_version_id"]
    profiles = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile").json()
    p = profiles[0]
    assert p["row_count"] == 5
    assert p["column_count"] == 4


def test_profile_csv_saved_in_repo(client: TestClient) -> None:
    upload = _upload_csv(client)
    dataset_id = upload["dataset"]["dataset_id"]
    version_id = upload["dataset_version"]["dataset_version_id"]
    profiles = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile").json()
    profile_id = profiles[0]["profile_id"]
    resp = client.get(f"/profiles/{profile_id}")
    assert resp.status_code == 200
    assert resp.json()["profile_id"] == profile_id


def test_profile_csv_has_column_profiles(client: TestClient) -> None:
    upload = _upload_csv(client)
    dataset_id = upload["dataset"]["dataset_id"]
    version_id = upload["dataset_version"]["dataset_version_id"]
    profiles = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile").json()
    assert len(profiles[0]["column_profiles"]) == 4


def test_profile_csv_revenue_metric(client: TestClient) -> None:
    upload = _upload_csv(client)
    dataset_id = upload["dataset"]["dataset_id"]
    version_id = upload["dataset_version"]["dataset_version_id"]
    profiles = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile").json()
    cols = {c["column_name"]: c for c in profiles[0]["column_profiles"]}
    assert cols["revenue"]["is_likely_metric"]


# ---------------------------------------------------------------------------
# Excel multi-sheet profiling via API
# ---------------------------------------------------------------------------


def test_profile_excel_two_profiles(client: TestClient, xlsx_bytes: bytes) -> None:
    upload = client.post(
        f"/workspaces/{WORKSPACE_ID}/datasets/upload",
        files={"file": ("sales.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    dataset_id = upload["dataset"]["dataset_id"]
    version_id = upload["dataset_version"]["dataset_version_id"]
    profiles = client.post(f"/datasets/{dataset_id}/versions/{version_id}/profile").json()
    assert len(profiles) == 2
    names = {p["table_name"] for p in profiles}
    assert "January" in names
    assert "February" in names


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_profile_unknown_version_404(client: TestClient) -> None:
    resp = client.post(f"/datasets/{uuid4()}/versions/{uuid4()}/profile")
    assert resp.status_code == 404


def test_get_unknown_profile_404(client: TestClient) -> None:
    resp = client.get(f"/profiles/{uuid4()}")
    assert resp.status_code == 404
