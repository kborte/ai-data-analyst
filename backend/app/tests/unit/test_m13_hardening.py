"""M13A: Tests for transaction boundaries and storage/DB consistency hardening."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest

from app.db.base import get_db


# ---------------------------------------------------------------------------
# 1. get_db() commit / rollback behaviour
# ---------------------------------------------------------------------------

class TestGetDb:
    def test_commits_when_no_exception(self):
        mock_session = MagicMock()
        with patch("app.db.base.SessionLocal", return_value=mock_session):
            gen = get_db()
            next(gen)  # yield point — simulate request body running
            try:
                next(gen)  # advance past yield → triggers commit + finally
            except StopIteration:
                pass
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()
        mock_session.close.assert_called_once()

    def test_rolls_back_and_reraises_on_exception(self):
        mock_session = MagicMock()
        with patch("app.db.base.SessionLocal", return_value=mock_session):
            gen = get_db()
            next(gen)
            with pytest.raises(ValueError, match="simulated"):
                gen.throw(ValueError("simulated"))
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()
        mock_session.close.assert_called_once()

    def test_close_called_even_after_rollback(self):
        mock_session = MagicMock()
        with patch("app.db.base.SessionLocal", return_value=mock_session):
            gen = get_db()
            next(gen)
            try:
                gen.throw(RuntimeError("boom"))
            except RuntimeError:
                pass
        mock_session.close.assert_called_once()

    def test_rollback_failure_does_not_hide_original_error(self):
        mock_session = MagicMock()
        mock_session.rollback.side_effect = Exception("rollback failed")
        with patch("app.db.base.SessionLocal", return_value=mock_session):
            gen = get_db()
            next(gen)
            with pytest.raises(Exception, match="rollback failed"):
                gen.throw(ValueError("original"))
        # close still called (finally block)
        mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Database repo save() uses flush(), not commit()
# ---------------------------------------------------------------------------

class TestRepoUsesFlush:
    """Spot-check that database repos call flush() not commit() on save()."""

    def _make_session(self):
        session = MagicMock()
        # merge returns the same row so _from_orm converters work
        session.merge.side_effect = lambda row: row
        return session

    def test_dataset_version_repo_uses_flush(self):
        from app.repositories.database import DatasetVersionRepository
        from app.schemas.dataset import DatasetVersion
        from app.schemas.common import DatasetVersionType
        from datetime import datetime, timezone

        session = self._make_session()
        # Provide a minimal ORM-like return from merge
        orm_row = MagicMock()
        orm_row.dataset_version_id = uuid4()
        orm_row.dataset_id = uuid4()
        orm_row.parent_version_id = None
        orm_row.version_number = 1
        orm_row.version_type = "original"
        orm_row.display_name = None
        orm_row.description = None
        orm_row.storage_path = None
        orm_row.storage_backend = None
        orm_row.storage_bucket = None
        orm_row.storage_format = None
        orm_row.row_count = None
        orm_row.column_count = None
        orm_row.created_by_user_id = uuid4()
        orm_row.created_at = datetime.now(timezone.utc)
        orm_row.metadata = {}
        session.merge.return_value = orm_row

        repo = DatasetVersionRepository(session)  # type: ignore[arg-type]
        version = DatasetVersion(
            dataset_version_id=orm_row.dataset_version_id,
            dataset_id=orm_row.dataset_id,
            version_number=1,
            version_type=DatasetVersionType.original,
            created_by_user_id=orm_row.created_by_user_id,
            created_at=orm_row.created_at,
        )
        repo.save(version)

        session.flush.assert_called_once()
        session.commit.assert_not_called()

    def test_saved_view_repo_uses_flush(self):
        from app.repositories.database import SavedViewRepository
        from app.schemas.saved_view import SavedView, SavedViewSourceType
        from datetime import datetime, timezone

        session = self._make_session()
        orm_row = MagicMock()
        orm_row.saved_view_id = uuid4()
        orm_row.workspace_id = uuid4()
        orm_row.dataset_id = uuid4()
        orm_row.dataset_version_id = uuid4()
        orm_row.name = "test"
        orm_row.description = None
        orm_row.source_type = "query"
        orm_row.source_spec_json = {}
        orm_row.storage_backend = None
        orm_row.storage_bucket = None
        orm_row.storage_path = None
        orm_row.storage_format = None
        orm_row.row_count = None
        orm_row.column_count = None
        orm_row.created_at = datetime.now(timezone.utc)
        orm_row.created_by_user_id = None
        session.merge.return_value = orm_row

        repo = SavedViewRepository(session)  # type: ignore[arg-type]
        view = SavedView(
            saved_view_id=orm_row.saved_view_id,
            workspace_id=orm_row.workspace_id,
            dataset_id=orm_row.dataset_id,
            dataset_version_id=orm_row.dataset_version_id,
            name="test",
            source_type=SavedViewSourceType.query,
            created_at=orm_row.created_at,
        )
        repo.save(view)

        session.flush.assert_called_once()
        session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# 3. save_view_from_table_result: best-effort storage cleanup on DB failure
# ---------------------------------------------------------------------------

class TestSaveViewStorageCleanup:
    def test_deletes_storage_artifact_when_repo_save_fails(self):
        from app.services.saved_artifacts import save_view_from_table_result
        from app.tools.files.storage_service import StoredFile

        workspace_id = uuid4()
        dataset_id = uuid4()

        saved_path_capture: list[str] = []

        def capture_save(path: str, data: bytes) -> StoredFile:
            saved_path_capture.append(path)
            return StoredFile(
                storage_backend="local",
                storage_bucket=None,
                storage_path=path,
            )

        mock_storage = MagicMock()
        mock_storage.save.side_effect = capture_save

        mock_repo = MagicMock()
        mock_repo.save.side_effect = RuntimeError("DB write failed")

        with pytest.raises(RuntimeError, match="DB write failed"):
            save_view_from_table_result(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                dataset_version_id=uuid4(),
                name="My View",
                columns=["a", "b"],
                rows=[[1, 2]],
                repo=mock_repo,
                storage=mock_storage,
            )

        # storage.delete must have been called with the same path that was saved
        assert len(saved_path_capture) == 1
        mock_storage.delete.assert_called_once_with(saved_path_capture[0])

    def test_original_error_raised_even_if_cleanup_also_fails(self):
        from app.services.saved_artifacts import save_view_from_table_result
        from app.tools.files.storage_service import StoredFile

        mock_storage = MagicMock()
        mock_storage.save.return_value = StoredFile(
            storage_backend="local", storage_bucket=None, storage_path="any/path.csv"
        )
        mock_storage.delete.side_effect = Exception("storage delete failed")

        mock_repo = MagicMock()
        mock_repo.save.side_effect = RuntimeError("DB write failed")

        # Must raise the original DB error, not the storage cleanup error
        with pytest.raises(RuntimeError, match="DB write failed"):
            save_view_from_table_result(
                workspace_id=uuid4(),
                dataset_id=uuid4(),
                dataset_version_id=uuid4(),
                name="My View",
                columns=["x"],
                rows=[[1]],
                repo=mock_repo,
                storage=mock_storage,
            )

    def test_returns_saved_view_when_both_writes_succeed(self):
        from app.services.saved_artifacts import save_view_from_table_result
        from app.schemas.saved_view import SavedView, SavedViewSourceType
        from app.tools.files.storage_service import StoredFile
        from datetime import datetime, timezone

        mock_storage = MagicMock()
        mock_storage.save.return_value = StoredFile(
            storage_backend="local",
            storage_bucket=None,
            storage_path="ws/ds/views/test.csv",
        )

        expected_view = SavedView(
            saved_view_id=uuid4(),
            workspace_id=uuid4(),
            dataset_id=uuid4(),
            dataset_version_id=uuid4(),
            name="My View",
            source_type=SavedViewSourceType.query,
            created_at=datetime.now(timezone.utc),
        )
        mock_repo = MagicMock()
        mock_repo.save.return_value = expected_view

        result = save_view_from_table_result(
            workspace_id=expected_view.workspace_id,
            dataset_id=expected_view.dataset_id,
            dataset_version_id=expected_view.dataset_version_id,
            name="My View",
            columns=["x"],
            rows=[[1]],
            repo=mock_repo,
            storage=mock_storage,
        )

        assert result is expected_view
        mock_storage.delete.assert_not_called()


# ---------------------------------------------------------------------------
# 4. upload_service: best-effort storage cleanup on metadata failure
# ---------------------------------------------------------------------------

class TestUploadServiceStorageCleanup:
    """Verify orphaned storage artifacts are cleaned up on metadata write failure."""

    def _make_upload_call(self, mock_storage, mock_repos, content=b"col\nval\n", filename="test.csv"):
        from app.services.upload_service import upload_dataset

        upload_dataset(
            workspace_id=uuid4(),
            content=content,
            filename=filename,
            storage=mock_storage,
            repos=mock_repos,
        )

    def _make_repos_with_failing_data_source(self):
        from app.dependencies import Repos
        mock_repos = Repos()
        mock_repos.data_source.save = MagicMock(side_effect=RuntimeError("DB down"))
        return mock_repos

    def test_cleanup_called_on_metadata_failure(self):
        from app.services.upload_service import upload_dataset
        from app.tools.files.storage_service import StoredFile

        mock_storage = MagicMock()
        mock_storage.save.return_value = StoredFile(
            storage_backend="local", storage_bucket=None, storage_path="some/path"
        )
        mock_repos = self._make_repos_with_failing_data_source()

        with pytest.raises(RuntimeError, match="DB down"):
            upload_dataset(
                workspace_id=uuid4(),
                content=b"col\nval\n",
                filename="test.csv",
                storage=mock_storage,
                repos=mock_repos,
                dataset_name=None,
            )

        # storage.delete must be called for cleanup (raw + duckdb artifacts)
        assert mock_storage.delete.call_count >= 1

    def test_original_db_error_raised_even_if_cleanup_fails(self):
        from app.services.upload_service import upload_dataset
        from app.tools.files.storage_service import StoredFile

        mock_storage = MagicMock()
        mock_storage.save.return_value = StoredFile(
            storage_backend="local", storage_bucket=None, storage_path="some/path"
        )
        mock_storage.delete.side_effect = Exception("delete failed")
        mock_repos = self._make_repos_with_failing_data_source()

        with pytest.raises(RuntimeError, match="DB down"):
            upload_dataset(
                workspace_id=uuid4(),
                content=b"col\nval\n",
                filename="test.csv",
                storage=mock_storage,
                repos=mock_repos,
                dataset_name=None,
            )
