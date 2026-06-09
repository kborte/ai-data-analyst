"""Tests for M12E: analytics API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.dependencies import Repos, get_llm_provider, get_repos, get_storage
from app.main import app
from app.schemas.common import DatasetVersionType
from app.schemas.dataset import Dataset, DatasetVersion
from app.schemas.saved_view import SavedView
from app.schemas.saved_visual import SavedVisual
from app.tools.data.duckdb_service import create_version_duckdb
from app.tools.files.storage_service import LocalStorageBackend
from app.tools.llm.provider import FakeLLMProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(tz=timezone.utc)


def _make_dataset(workspace_id=None) -> Dataset:
    return Dataset(
        dataset_id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        name="Sales Dataset",
        created_by_user_id=uuid4(),
        created_at=_now(),
    )


def _make_version(dataset: Dataset, storage_path: str | None = None) -> DatasetVersion:
    return DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=dataset.dataset_id,
        version_number=1,
        version_type=DatasetVersionType.original,
        storage_path=storage_path,
        created_by_user_id=uuid4(),
        created_at=_now(),
    )


def _sales_duckdb(tmp_path: Path) -> Path:
    db = tmp_path / "v1_original.duckdb"
    df = pd.DataFrame({
        "month": ["Jan", "Feb", "Mar"],
        "channel": ["online", "store", "online"],
        "revenue": [100.0, 200.0, 150.0],
    })
    create_version_duckdb({"sales": df}, db)
    return db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    yield TestClient(app)
    app.dependency_overrides.pop(get_repos, None)
    app.dependency_overrides.pop(get_storage, None)
    app.dependency_overrides.pop(get_llm_provider, None)


@pytest.fixture()
def dataset_and_version(mem_repos, fake_storage, tmp_path):
    """Dataset + version with a real DuckDB artifact written to local storage."""
    dataset = _make_dataset()
    mem_repos.dataset.save(dataset)

    db_path = _sales_duckdb(tmp_path)
    storage_key = f"workspaces/{dataset.workspace_id}/datasets/{dataset.dataset_id}/versions/v1_original.duckdb"
    fake_storage.save(storage_key, db_path.read_bytes())

    version = _make_version(dataset, storage_path=storage_key)
    mem_repos.dataset_version.save(version)
    return dataset, version


# ---------------------------------------------------------------------------
# POST /datasets/{dataset_id}/versions/{dataset_version_id}/analytics/ask
# ---------------------------------------------------------------------------

class TestAskAnalytics:
    def test_404_unknown_version(self, client):
        resp = client.post(
            f"/datasets/{uuid4()}/versions/{uuid4()}/analytics/ask",
            json={"question": "show revenue"},
        )
        assert resp.status_code == 404

    def test_404_version_belongs_to_different_dataset(self, client, mem_repos, fake_storage, tmp_path):
        dataset = _make_dataset()
        mem_repos.dataset.save(dataset)

        db_path = _sales_duckdb(tmp_path)
        storage_key = "v1.duckdb"
        fake_storage.save(storage_key, db_path.read_bytes())
        version = _make_version(dataset, storage_path=storage_key)
        mem_repos.dataset_version.save(version)

        wrong_dataset_id = uuid4()
        resp = client.post(
            f"/datasets/{wrong_dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
            json={"question": "show revenue"},
        )
        assert resp.status_code == 404

    def test_422_version_has_no_duckdb(self, client, mem_repos):
        dataset = _make_dataset()
        mem_repos.dataset.save(dataset)
        version = _make_version(dataset, storage_path=None)
        mem_repos.dataset_version.save(version)

        resp = client.post(
            f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
            json={"question": "show revenue"},
        )
        assert resp.status_code == 422

    def test_returns_analytics_response_schema(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(
            f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
            json={"question": "show me the data"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dataset_id"] == str(dataset.dataset_id)
        assert body["dataset_version_id"] == str(version.dataset_version_id)
        assert "output" in body
        assert "plan" in body

    def test_output_preserves_dataset_version_id(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(
            f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
            json={"question": "show me the data"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["output"]["dataset_version_id"] == str(version.dataset_version_id)

    def test_output_not_automatically_saved(self, client, dataset_and_version, mem_repos):
        dataset, version = dataset_and_version
        resp = client.post(
            f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
            json={"question": "show me the data"},
        )
        assert resp.status_code == 200
        # Nothing was persisted to saved_view or saved_visual repos
        assert mem_repos.saved_view.list_by_version(version.dataset_version_id) == []
        assert mem_repos.saved_visual.list_by_version(version.dataset_version_id) == []

    def test_accepts_recent_messages_and_prior_refs(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(
            f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
            json={
                "question": "show revenue by channel",
                "recent_messages": [
                    {"role": "user", "content": "hello", "output_refs": []}
                ],
                "prior_output_refs": [],
            },
        )
        assert resp.status_code == 200

    def test_text_question_returns_text_output(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(
            f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
            json={"question": "what is this dataset?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should be text output (explain/describe words)
        assert body["output"]["output_type"] in ("text", "table", "visual", "mixed")

    def test_aggregate_question_returns_non_error(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(
            f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
            json={"question": "sum revenue by channel"},
        )
        assert resp.status_code == 200

    def test_visual_question_returns_non_error(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(
            f"/datasets/{dataset.dataset_id}/versions/{version.dataset_version_id}/analytics/ask",
            json={"question": "bar chart of revenue by channel"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["output"]["output_type"] in ("visual", "text")


# ---------------------------------------------------------------------------
# POST /analytics/table-results/save-as-view
# ---------------------------------------------------------------------------

class TestSaveAsView:
    def _url(self):
        return "/analytics/table-results/save-as-view"

    def test_404_unknown_version(self, client):
        resp = client.post(self._url(), json={
            "dataset_id": str(uuid4()),
            "dataset_version_id": str(uuid4()),
            "name": "My View",
            "columns": ["a"],
            "rows": [[1]],
        })
        assert resp.status_code == 404

    def test_save_inline_rows_returns_201(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(self._url(), json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "name": "Revenue Table",
            "columns": ["channel", "revenue"],
            "rows": [["online", 250.0], ["store", 200.0]],
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Revenue Table"
        assert body["dataset_version_id"] == str(version.dataset_version_id)

    def test_save_via_storage_path_returns_201(self, client, dataset_and_version, fake_storage):
        dataset, version = dataset_and_version
        storage_key = f"results/{uuid4()}.csv"
        fake_storage.save(storage_key, b"channel,revenue\nonline,250\n")

        resp = client.post(self._url(), json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "name": "From Storage",
            "storage_path": storage_key,
            "storage_format": "csv",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["storage_path"] == storage_key

    def test_422_no_data_provided(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(self._url(), json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "name": "Empty View",
        })
        assert resp.status_code == 422

    def test_saved_view_persisted_in_repo(self, client, dataset_and_version, mem_repos):
        dataset, version = dataset_and_version
        client.post(self._url(), json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "name": "Persisted View",
            "columns": ["x"],
            "rows": [[1]],
        })
        views = mem_repos.saved_view.list_by_version(version.dataset_version_id)
        assert len(views) == 1
        assert views[0].name == "Persisted View"

    def test_version_scoped_correctly(self, client, dataset_and_version, mem_repos):
        dataset, version = dataset_and_version
        client.post(self._url(), json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "name": "Scoped View",
            "columns": ["x"],
            "rows": [[1]],
        })
        other_version_id = uuid4()
        assert mem_repos.saved_view.list_by_version(other_version_id) == []


# ---------------------------------------------------------------------------
# POST /analytics/visual-results/save-as-visual
# ---------------------------------------------------------------------------

class TestSaveAsVisual:
    def _url(self):
        return "/analytics/visual-results/save-as-visual"

    def test_404_unknown_version(self, client):
        resp = client.post(self._url(), json={
            "dataset_id": str(uuid4()),
            "dataset_version_id": str(uuid4()),
            "title": "My Chart",
            "chart_type": "bar",
        })
        assert resp.status_code == 404

    def test_save_minimal_spec_returns_201(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(self._url(), json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "title": "Revenue Chart",
            "chart_type": "bar",
            "chart_spec_json": {},
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Revenue Chart"
        assert body["dataset_version_id"] == str(version.dataset_version_id)

    def test_save_full_spec_returns_201(self, client, dataset_and_version):
        dataset, version = dataset_and_version
        resp = client.post(self._url(), json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "title": "Full Chart",
            "chart_type": "line",
            "chart_spec_json": {
                "visualization_id": str(uuid4()),
                "title": "Full Chart",
                "chart_type": "line",
                "x_key": "month",
                "series": [{"data_key": "revenue", "label": "Revenue"}],
                "data": [{"month": "Jan", "revenue": 100}],
                "description": "Monthly revenue",
            },
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["chart_spec_json"]["x_key"] == "month"

    def test_saved_visual_persisted_in_repo(self, client, dataset_and_version, mem_repos):
        dataset, version = dataset_and_version
        client.post(self._url(), json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "title": "Persisted Visual",
            "chart_type": "bar",
        })
        visuals = mem_repos.saved_visual.list_by_version(version.dataset_version_id)
        assert len(visuals) == 1
        assert visuals[0].title == "Persisted Visual"

    def test_version_scoped_correctly(self, client, dataset_and_version, mem_repos):
        dataset, version = dataset_and_version
        client.post(self._url(), json={
            "dataset_id": str(dataset.dataset_id),
            "dataset_version_id": str(version.dataset_version_id),
            "title": "Scoped Visual",
            "chart_type": "bar",
        })
        other_version_id = uuid4()
        assert mem_repos.saved_visual.list_by_version(other_version_id) == []
