"""Tests for M11C: saved visual schema, repository, and API routes."""

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_repos, get_storage
from app.main import app
from app.repositories.memory import SavedVisualRepository
from app.schemas.dataset import Dataset
from app.schemas.saved_visual import SavedVisual, SavedVisualSourceType
from app.tools.files.storage_service import LocalStorageBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dataset() -> Dataset:
    return Dataset(
        dataset_id=uuid4(),
        workspace_id=uuid4(),
        name="DS",
        created_by_user_id=uuid4(),
        created_at=datetime.now(tz=timezone.utc),
    )


def _make_visual(dataset: Dataset, dataset_version_id=None, **kwargs) -> SavedVisual:
    defaults = dict(
        visual_id=uuid4(),
        workspace_id=dataset.workspace_id,
        dataset_id=dataset.dataset_id,
        dataset_version_id=dataset_version_id or uuid4(),
        title="My Chart",
        chart_type="bar",
        source_type=SavedVisualSourceType.chart_spec,
        created_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(kwargs)
    return SavedVisual(**defaults)


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
# Schema tests
# ---------------------------------------------------------------------------

class TestSavedVisualSchema:
    def test_all_source_types_valid(self):
        ds = _make_dataset()
        for stype in SavedVisualSourceType:
            v = _make_visual(ds, source_type=stype)
            assert v.source_type == stype

    def test_optional_fields_default_none(self):
        ds = _make_dataset()
        v = _make_visual(ds)
        assert v.description is None
        assert v.source_visualization_result_id is None
        assert v.source_view_id is None
        assert v.data_storage_backend is None
        assert v.data_storage_path is None
        assert v.created_by_user_id is None

    def test_default_dicts_empty(self):
        ds = _make_dataset()
        v = _make_visual(ds)
        assert v.chart_spec_json == {}
        assert v.source_spec_json == {}
        assert v.metadata_json == {}

    def test_chart_spec_stored_inline(self):
        ds = _make_dataset()
        spec = {"title": "Revenue", "data": [{"x": "Jan", "y": 100}]}
        v = _make_visual(ds, chart_spec_json=spec)
        assert v.chart_spec_json["title"] == "Revenue"
        assert len(v.chart_spec_json["data"]) == 1

    def test_source_visualization_result_reference(self):
        ds = _make_dataset()
        result_id = uuid4()
        v = _make_visual(
            ds,
            source_type=SavedVisualSourceType.visualization_result,
            source_visualization_result_id=result_id,
        )
        assert v.source_visualization_result_id == result_id


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------

class TestSavedVisualRepository:
    def test_save_and_get(self):
        repo = SavedVisualRepository()
        ds = _make_dataset()
        v = _make_visual(ds)
        repo.save(v)
        fetched = repo.get(v.visual_id)
        assert fetched is not None
        assert fetched.visual_id == v.visual_id

    def test_get_missing_returns_none(self):
        repo = SavedVisualRepository()
        assert repo.get(uuid4()) is None

    def test_list_by_version_filters_correctly(self):
        repo = SavedVisualRepository()
        ds = _make_dataset()
        vid = uuid4()
        v1 = _make_visual(ds, dataset_version_id=vid, title="A")
        v2 = _make_visual(ds, dataset_version_id=vid, title="B")
        other = _make_visual(ds, title="C")
        repo.save(v1); repo.save(v2); repo.save(other)
        results = repo.list_by_version(vid)
        assert len(results) == 2
        assert {r.title for r in results} == {"A", "B"}

    def test_list_by_version_empty(self):
        assert SavedVisualRepository().list_by_version(uuid4()) == []

    def test_list_by_dataset_filters_correctly(self):
        repo = SavedVisualRepository()
        ds = _make_dataset()
        ds2 = _make_dataset()
        v1 = _make_visual(ds, title="X")
        v2 = _make_visual(ds, title="Y")
        other = _make_visual(ds2, title="Z")
        repo.save(v1); repo.save(v2); repo.save(other)
        results = repo.list_by_dataset(ds.dataset_id)
        assert len(results) == 2

    def test_delete_existing(self):
        repo = SavedVisualRepository()
        ds = _make_dataset()
        v = _make_visual(ds)
        repo.save(v)
        assert repo.delete(v.visual_id) is True
        assert repo.get(v.visual_id) is None

    def test_delete_missing_returns_false(self):
        assert SavedVisualRepository().delete(uuid4()) is False

    def test_save_overwrites(self):
        repo = SavedVisualRepository()
        ds = _make_dataset()
        v = _make_visual(ds, title="Old")
        repo.save(v)
        repo.save(v.model_copy(update={"title": "New"}))
        assert repo.get(v.visual_id).title == "New"

    def test_list_sorted_newest_first(self):
        from datetime import timedelta
        repo = SavedVisualRepository()
        ds = _make_dataset()
        vid = uuid4()
        old = _make_visual(ds, dataset_version_id=vid, title="old")
        new = old.model_copy(update={
            "visual_id": uuid4(),
            "title": "new",
            "created_at": old.created_at + timedelta(seconds=5),
        })
        repo.save(old); repo.save(new)
        assert repo.list_by_version(vid)[0].title == "new"


# ---------------------------------------------------------------------------
# API route tests
# ---------------------------------------------------------------------------

def test_list_visuals_empty(client):
    resp = client.get(f"/datasets/{uuid4()}/versions/{uuid4()}/visuals")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_visuals_by_version(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    vid = uuid4()
    v1 = _make_visual(ds, dataset_version_id=vid, title="A")
    v2 = _make_visual(ds, dataset_version_id=vid, title="B")
    other = _make_visual(ds, title="C")
    mem_repos.saved_visual.save(v1)
    mem_repos.saved_visual.save(v2)
    mem_repos.saved_visual.save(other)
    resp = client.get(f"/datasets/{ds.dataset_id}/versions/{vid}/visuals")
    assert resp.status_code == 200
    assert {r["title"] for r in resp.json()} == {"A", "B"}


def test_create_visual_returns_201(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    vid = uuid4()
    payload = {
        "title": "Revenue Bar",
        "chart_type": "bar",
        "source_type": "chart_spec",
        "chart_spec_json": {"data": [{"x": "Jan", "y": 500}]},
    }
    resp = client.post(f"/datasets/{ds.dataset_id}/versions/{vid}/visuals", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Revenue Bar"
    assert data["chart_type"] == "bar"
    assert data["dataset_id"] == str(ds.dataset_id)
    assert data["workspace_id"] == str(ds.workspace_id)


def test_create_visual_dataset_not_found(client):
    payload = {"title": "X", "chart_type": "line", "source_type": "direct"}
    resp = client.post(f"/datasets/{uuid4()}/versions/{uuid4()}/visuals", json=payload)
    assert resp.status_code == 404


def test_create_visual_with_viz_result_reference(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    result_id = uuid4()
    payload = {
        "title": "Linked Chart",
        "chart_type": "line",
        "source_type": "visualization_result",
        "source_visualization_result_id": str(result_id),
    }
    resp = client.post(f"/datasets/{ds.dataset_id}/versions/{uuid4()}/visuals", json=payload)
    assert resp.status_code == 201
    assert resp.json()["source_visualization_result_id"] == str(result_id)


def test_get_visual_not_found(client):
    resp = client.get(f"/visuals/{uuid4()}")
    assert resp.status_code == 404


def test_get_visual_found(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    v = _make_visual(ds, title="My Line Chart")
    mem_repos.saved_visual.save(v)
    resp = client.get(f"/visuals/{v.visual_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "My Line Chart"


def test_delete_visual_not_found(client):
    resp = client.delete(f"/visuals/{uuid4()}")
    assert resp.status_code == 404


def test_delete_visual_removes_from_repo(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    v = _make_visual(ds)
    mem_repos.saved_visual.save(v)
    resp = client.delete(f"/visuals/{v.visual_id}")
    assert resp.status_code == 204
    assert mem_repos.saved_visual.get(v.visual_id) is None


def test_delete_visual_removes_data_artifact(client, mem_repos, fake_storage):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    path = f"workspaces/{ds.workspace_id}/visuals/data.json"
    fake_storage.save(path, b'{"data":[]}')
    v = _make_visual(ds, data_storage_path=path, data_storage_backend="local")
    mem_repos.saved_visual.save(v)
    client.delete(f"/visuals/{v.visual_id}")
    assert not fake_storage.exists(path)


def test_get_visual_data_inline(client, mem_repos):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    spec = {"data": [{"x": "Jan", "y": 100}, {"x": "Feb", "y": 200}]}
    v = _make_visual(ds, chart_spec_json=spec)
    mem_repos.saved_visual.save(v)
    resp = client.get(f"/visuals/{v.visual_id}/data")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert len(body["data"]) == 2


def test_get_visual_data_from_storage(client, mem_repos, fake_storage):
    ds = _make_dataset()
    mem_repos.dataset.save(ds)
    path = f"workspaces/{ds.workspace_id}/visuals/d.json"
    stored = json.dumps({"data": [{"x": "Q1", "y": 999}]}).encode()
    fake_storage.save(path, stored)
    v = _make_visual(ds, data_storage_path=path, data_storage_backend="local")
    mem_repos.saved_visual.save(v)
    resp = client.get(f"/visuals/{v.visual_id}/data")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"][0]["y"] == 999


def test_get_visual_data_not_found(client):
    resp = client.get(f"/visuals/{uuid4()}/data")
    assert resp.status_code == 404


def test_visualization_result_not_auto_saved(mem_repos):
    """VisualizationResult in the repo should NOT automatically become a SavedVisual."""
    assert len(mem_repos.saved_visual.list_by_dataset(uuid4())) == 0
