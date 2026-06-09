"""Tests for M11B: saved view API routes."""

import csv
import io
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
from app.schemas.dataset import Dataset
from app.schemas.saved_view import SavedView, SavedViewSourceType
from app.tools.files.storage_service import LocalStorageBackend


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_dataset(workspace_id=None) -> Dataset:
    return Dataset(
        dataset_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        name="Test Dataset",
        created_by_user_id=uuid4(),
        created_at=datetime.now(tz=timezone.utc),
    )


def _make_view(dataset: Dataset, dataset_version_id=None, **kwargs) -> SavedView:
    defaults = dict(
        saved_view_id=uuid4(),
        workspace_id=dataset.workspace_id,
        dataset_id=dataset.dataset_id,
        dataset_version_id=dataset_version_id or uuid4(),
        name="My View",
        source_type=SavedViewSourceType.query,
        created_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(kwargs)
    return SavedView(**defaults)


def _csv_bytes(columns: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


@pytest.fixture()
def mem_repos():
    return Repos()


@pytest.fixture()
def fake_storage(tmp_path):
    return LocalStorageBackend(base_dir=str(tmp_path))


@pytest.fixture()
def client(mem_repos, fake_storage):
    app.dependency_overrides[get_repos] = lambda: mem_repos
    app.dependency_overrides[get_storage] = lambda: fake_storage
    yield TestClient(app)
    app.dependency_overrides.pop(get_repos, None)
    app.dependency_overrides.pop(get_storage, None)


# ---------------------------------------------------------------------------
# List views
# ---------------------------------------------------------------------------

def test_list_views_empty(client):
    resp = client.get(f"/datasets/{uuid4()}/versions/{uuid4()}/views")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_views_returns_only_matching_version(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    vid = uuid4()
    v1 = _make_view(ds, dataset_version_id=vid, name="A")
    v2 = _make_view(ds, dataset_version_id=vid, name="B")
    other = _make_view(ds, name="C")  # different version
    mem_repos.saved_view.save(v1)
    mem_repos.saved_view.save(v2)
    mem_repos.saved_view.save(other)
    resp = client.get(f"/datasets/{ds.dataset_id}/versions/{vid}/views")
    assert resp.status_code == 200
    names = {r["name"] for r in resp.json()}
    assert names == {"A", "B"}


# ---------------------------------------------------------------------------
# Create view
# ---------------------------------------------------------------------------

def test_create_view_returns_201(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    vid = uuid4()
    payload = {"name": "Revenue Summary", "source_type": "aggregation"}
    resp = client.post(f"/datasets/{ds.dataset_id}/versions/{vid}/views", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Revenue Summary"
    assert data["source_type"] == "aggregation"
    assert data["dataset_id"] == str(ds.dataset_id)
    assert data["dataset_version_id"] == str(vid)
    assert data["workspace_id"] == str(ds.workspace_id)


def test_create_view_dataset_not_found(client):
    vid = uuid4()
    payload = {"name": "X", "source_type": "query"}
    resp = client.post(f"/datasets/{uuid4()}/versions/{vid}/views", json=payload)
    assert resp.status_code == 404


def test_create_view_persisted_in_repo(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    vid = uuid4()
    payload = {"name": "Saved", "source_type": "filter"}
    resp = client.post(f"/datasets/{ds.dataset_id}/versions/{vid}/views", json=payload)
    from uuid import UUID
    view_id = UUID(resp.json()["saved_view_id"])
    fetched = mem_repos.saved_view.get(view_id)
    assert fetched is not None
    assert fetched.name == "Saved"


# ---------------------------------------------------------------------------
# Get view
# ---------------------------------------------------------------------------

def test_get_view_not_found(client):
    resp = client.get(f"/views/{uuid4()}")
    assert resp.status_code == 404


def test_get_view_found(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    view = _make_view(ds, name="Detail View")
    mem_repos.saved_view.save(view)
    resp = client.get(f"/views/{view.saved_view_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Detail View"


# ---------------------------------------------------------------------------
# Delete view
# ---------------------------------------------------------------------------

def test_delete_view_not_found(client):
    resp = client.delete(f"/views/{uuid4()}")
    assert resp.status_code == 404


def test_delete_view_removes_from_repo(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    view = _make_view(ds)
    mem_repos.saved_view.save(view)
    resp = client.delete(f"/views/{view.saved_view_id}")
    assert resp.status_code == 204
    assert mem_repos.saved_view.get(view.saved_view_id) is None


def test_delete_view_removes_artifact_from_storage(client, mem_repos, fake_storage):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    path = f"workspaces/{ds.workspace_id}/datasets/{ds.dataset_id}/views/test.csv"
    fake_storage.save(path, b"col\n1\n")
    view = _make_view(ds, storage_path=path, storage_format="csv")
    mem_repos.saved_view.save(view)
    client.delete(f"/views/{view.saved_view_id}")
    assert not fake_storage.exists(path)


def test_delete_view_succeeds_when_no_artifact(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    view = _make_view(ds, storage_path=None)
    mem_repos.saved_view.save(view)
    resp = client.delete(f"/views/{view.saved_view_id}")
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def test_preview_not_found(client):
    resp = client.get(f"/views/{uuid4()}/preview")
    assert resp.status_code == 404


def test_preview_no_artifact_returns_empty(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    view = _make_view(ds, storage_path=None)
    mem_repos.saved_view.save(view)
    resp = client.get(f"/views/{view.saved_view_id}/preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["columns"] == []
    assert data["rows"] == []
    assert data["preview_row_count"] == 0


def test_preview_returns_columns_and_rows(client, mem_repos, fake_storage):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    columns = ["month", "revenue"]
    rows = [["Jan", "1000"], ["Feb", "2000"], ["Mar", "3000"]]
    path = f"workspaces/{ds.workspace_id}/datasets/{ds.dataset_id}/views/v.csv"
    fake_storage.save(path, _csv_bytes(columns, rows))
    view = _make_view(ds, storage_path=path, storage_format="csv", row_count=3)
    mem_repos.saved_view.save(view)
    resp = client.get(f"/views/{view.saved_view_id}/preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["columns"] == ["month", "revenue"]
    assert len(data["rows"]) == 3
    assert data["preview_row_count"] == 3
    assert data["total_rows_in_artifact"] == 3


def test_preview_caps_at_row_limit(client, mem_repos, fake_storage):
    from app.schemas.saved_view import PREVIEW_ROW_LIMIT
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    data_rows = [[str(i)] for i in range(PREVIEW_ROW_LIMIT + 50)]
    path = f"workspaces/{ds.workspace_id}/datasets/{ds.dataset_id}/views/big.csv"
    fake_storage.save(path, _csv_bytes(["n"], data_rows))
    view = _make_view(ds, storage_path=path, storage_format="csv")
    mem_repos.saved_view.save(view)
    resp = client.get(f"/views/{view.saved_view_id}/preview")
    assert resp.status_code == 200
    assert resp.json()["preview_row_count"] == PREVIEW_ROW_LIMIT


def test_preview_unsupported_format_returns_415(client, mem_repos, fake_storage):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    view = _make_view(ds, storage_path="some/path.parquet", storage_format="parquet")
    mem_repos.saved_view.save(view)
    resp = client.get(f"/views/{view.saved_view_id}/preview")
    assert resp.status_code == 415


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def test_download_not_found(client):
    resp = client.get(f"/views/{uuid4()}/download")
    assert resp.status_code == 404


def test_download_csv(client, mem_repos, fake_storage):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    path = f"workspaces/{ds.workspace_id}/datasets/{ds.dataset_id}/views/out.csv"
    csv_data = _csv_bytes(["a", "b"], [["1", "2"]])
    fake_storage.save(path, csv_data)
    view = _make_view(ds, name="My Export", storage_path=path, storage_format="csv")
    mem_repos.saved_view.save(view)
    resp = client.get(f"/views/{view.saved_view_id}/download?format=csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "My_Export.csv" in resp.headers["content-disposition"]
    assert resp.content == csv_data


def test_download_unsupported_format_returns_400(client, mem_repos, fake_storage):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    path = "some/path.csv"
    fake_storage.save(path, b"x")
    view = _make_view(ds, storage_path=path, storage_format="csv")
    mem_repos.saved_view.save(view)
    resp = client.get(f"/views/{view.saved_view_id}/download?format=xlsx")
    assert resp.status_code == 400


def test_download_no_artifact_returns_404(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    view = _make_view(ds, storage_path=None)
    mem_repos.saved_view.save(view)
    resp = client.get(f"/views/{view.saved_view_id}/download?format=csv")
    assert resp.status_code == 404
