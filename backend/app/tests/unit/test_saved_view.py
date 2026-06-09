"""Tests for M11A: saved view schemas, repository, and storage path helpers."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.repositories.memory import SavedViewRepository
from app.schemas.saved_view import SavedView, SavedViewSourceType
from app.tools.files.storage_service import saved_view_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WID = uuid4()
DID = uuid4()
VID = uuid4()


def _make_view(
    *,
    name: str = "Test View",
    source_type: SavedViewSourceType = SavedViewSourceType.query,
    dataset_id=None,
    dataset_version_id=None,
    workspace_id=None,
) -> SavedView:
    return SavedView(
        saved_view_id=uuid4(),
        workspace_id=workspace_id or WID,
        dataset_id=dataset_id or DID,
        dataset_version_id=dataset_version_id or VID,
        name=name,
        source_type=source_type,
        created_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestSavedViewSchema:
    def test_all_source_types_valid(self):
        for stype in SavedViewSourceType:
            v = _make_view(source_type=stype)
            assert v.source_type == stype

    def test_optional_fields_default_none(self):
        v = _make_view()
        assert v.description is None
        assert v.storage_backend is None
        assert v.storage_path is None
        assert v.storage_format is None
        assert v.row_count is None
        assert v.column_count is None
        assert v.created_by_user_id is None

    def test_default_dicts_empty(self):
        v = _make_view()
        assert v.source_spec_json == {}
        assert v.metadata_json == {}

    def test_with_storage_metadata(self):
        v = SavedView(
            saved_view_id=uuid4(),
            workspace_id=WID,
            dataset_id=DID,
            dataset_version_id=VID,
            name="Sales Summary",
            source_type=SavedViewSourceType.aggregation,
            storage_backend="local",
            storage_path="workspaces/x/datasets/y/views/z.csv",
            storage_format="csv",
            row_count=100,
            column_count=5,
            created_at=datetime.now(tz=timezone.utc),
        )
        assert v.row_count == 100
        assert v.storage_format == "csv"


# ---------------------------------------------------------------------------
# Storage path helper
# ---------------------------------------------------------------------------

class TestSavedViewPath:
    def test_path_structure(self):
        wid, did, view_id = uuid4(), uuid4(), uuid4()
        path = saved_view_path(wid, did, view_id, "csv")
        assert path == f"workspaces/{wid}/datasets/{did}/views/{view_id}.csv"

    def test_parquet_format(self):
        wid, did, view_id = uuid4(), uuid4(), uuid4()
        path = saved_view_path(wid, did, view_id, "parquet")
        assert path.endswith(".parquet")

    def test_json_format(self):
        wid, did, view_id = uuid4(), uuid4(), uuid4()
        path = saved_view_path(wid, did, view_id, "json")
        assert path.endswith(".json")

    def test_ids_in_path(self):
        wid, did, view_id = uuid4(), uuid4(), uuid4()
        path = saved_view_path(wid, did, view_id, "csv")
        assert str(wid) in path
        assert str(did) in path
        assert str(view_id) in path


# ---------------------------------------------------------------------------
# Memory repository
# ---------------------------------------------------------------------------

class TestSavedViewRepository:
    def test_save_and_get(self):
        repo = SavedViewRepository()
        view = _make_view()
        saved = repo.save(view)
        fetched = repo.get(saved.saved_view_id)
        assert fetched is not None
        assert fetched.saved_view_id == saved.saved_view_id
        assert fetched.name == "Test View"

    def test_get_missing_returns_none(self):
        repo = SavedViewRepository()
        assert repo.get(uuid4()) is None

    def test_list_by_version(self):
        repo = SavedViewRepository()
        vid = uuid4()
        v1 = _make_view(name="A", dataset_version_id=vid)
        v2 = _make_view(name="B", dataset_version_id=vid)
        v3 = _make_view(name="C")  # different version
        repo.save(v1)
        repo.save(v2)
        repo.save(v3)
        results = repo.list_by_version(vid)
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"A", "B"}

    def test_list_by_version_empty(self):
        repo = SavedViewRepository()
        assert repo.list_by_version(uuid4()) == []

    def test_list_by_dataset(self):
        repo = SavedViewRepository()
        did = uuid4()
        v1 = _make_view(name="X", dataset_id=did)
        v2 = _make_view(name="Y", dataset_id=did)
        v3 = _make_view(name="Z")  # different dataset
        repo.save(v1)
        repo.save(v2)
        repo.save(v3)
        results = repo.list_by_dataset(did)
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"X", "Y"}

    def test_list_by_dataset_empty(self):
        repo = SavedViewRepository()
        assert repo.list_by_dataset(uuid4()) == []

    def test_delete_existing(self):
        repo = SavedViewRepository()
        view = _make_view()
        repo.save(view)
        assert repo.delete(view.saved_view_id) is True
        assert repo.get(view.saved_view_id) is None

    def test_delete_missing_returns_false(self):
        repo = SavedViewRepository()
        assert repo.delete(uuid4()) is False

    def test_save_overwrites(self):
        repo = SavedViewRepository()
        view = _make_view(name="Old Name")
        repo.save(view)
        updated = view.model_copy(update={"name": "New Name"})
        repo.save(updated)
        fetched = repo.get(view.saved_view_id)
        assert fetched.name == "New Name"

    def test_list_by_version_sorted_newest_first(self):
        repo = SavedViewRepository()
        vid = uuid4()
        old = _make_view(name="old", dataset_version_id=vid)
        from datetime import timedelta
        new = old.model_copy(update={
            "saved_view_id": uuid4(),
            "name": "new",
            "created_at": old.created_at + timedelta(seconds=10),
        })
        repo.save(old)
        repo.save(new)
        results = repo.list_by_version(vid)
        assert results[0].name == "new"

    def test_list_by_dataset_sorted_newest_first(self):
        repo = SavedViewRepository()
        did = uuid4()
        old = _make_view(name="old", dataset_id=did)
        from datetime import timedelta
        new = old.model_copy(update={
            "saved_view_id": uuid4(),
            "name": "new",
            "created_at": old.created_at + timedelta(seconds=10),
        })
        repo.save(old)
        repo.save(new)
        results = repo.list_by_dataset(did)
        assert results[0].name == "new"

    def test_multiple_source_types_persisted(self):
        repo = SavedViewRepository()
        types = [
            SavedViewSourceType.query,
            SavedViewSourceType.aggregation,
            SavedViewSourceType.filter,
            SavedViewSourceType.feature_result,
            SavedViewSourceType.visualization_result,
        ]
        did = uuid4()
        for stype in types:
            repo.save(_make_view(source_type=stype, dataset_id=did))
        results = repo.list_by_dataset(did)
        persisted_types = {r.source_type for r in results}
        assert persisted_types == set(types)
