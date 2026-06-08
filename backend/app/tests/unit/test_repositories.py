from datetime import UTC, datetime
from uuid import uuid4

from app.repositories.memory import (
    ContextDocumentRepository,
    DatasetRepository,
    DatasetSourceRepository,
    DatasetTableRepository,
    DatasetVersionRepository,
    DataSourceRepository,
    UploadedFileRepository,
)
from app.schemas.common import (
    DatasetSourceRole,
    DatasetVersionType,
    DataSourceKind,
    UploadedFileKind,
)
from app.schemas.context_document import ContextDocument
from app.schemas.dataset import Dataset, DatasetSource, DatasetTable, DatasetVersion
from app.schemas.source import DataSource, UploadedFile

NOW = datetime.now(tz=UTC)


def test_data_source_save_and_get() -> None:
    repo = DataSourceRepository()
    wid = uuid4()
    ds = DataSource(
        data_source_id=uuid4(),
        workspace_id=wid,
        source_kind=DataSourceKind.uploaded_file,
        display_name="Sales CSV",
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    repo.save(ds)
    assert repo.get(ds.data_source_id) == ds
    assert ds in repo.list_by_workspace(wid)


def test_uploaded_file_save_and_get() -> None:
    repo = UploadedFileRepository()
    sid = uuid4()
    uf = UploadedFile(
        file_id=uuid4(),
        workspace_id=uuid4(),
        data_source_id=sid,
        file_kind=UploadedFileKind.csv,
        original_filename="sales.csv",
        storage_path="storage/uploads/workspaces/w/sources/s/original/f__sales.csv",
        size_bytes=1024,
        uploaded_by_user_id=uuid4(),
        uploaded_at=NOW,
    )
    repo.save(uf)
    assert repo.get(uf.file_id) == uf
    assert uf in repo.list_by_source(sid)


def test_dataset_save_and_get() -> None:
    repo = DatasetRepository()
    wid = uuid4()
    d = Dataset(
        dataset_id=uuid4(),
        workspace_id=wid,
        name="May Revenue",
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    repo.save(d)
    assert repo.get(d.dataset_id) == d
    assert d in repo.list_by_workspace(wid)


def test_dataset_source_save_and_get() -> None:
    repo = DatasetSourceRepository()
    did = uuid4()
    ds = DatasetSource(
        dataset_source_id=uuid4(),
        dataset_id=did,
        data_source_id=uuid4(),
        role=DatasetSourceRole.primary,
    )
    repo.save(ds)
    assert repo.get(ds.dataset_source_id) == ds
    assert ds in repo.list_by_dataset(did)


def test_dataset_version_save_and_get() -> None:
    repo = DatasetVersionRepository()
    did = uuid4()
    v = DatasetVersion(
        dataset_version_id=uuid4(),
        dataset_id=did,
        version_number=1,
        version_type=DatasetVersionType.original,
        display_name="Original upload",
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    repo.save(v)
    assert repo.get(v.dataset_version_id) == v
    assert v in repo.list_by_dataset(did)


def test_dataset_table_save_and_get() -> None:
    repo = DatasetTableRepository()
    vid = uuid4()
    t = DatasetTable(
        table_id=uuid4(),
        dataset_version_id=vid,
        table_name="sheet1",
    )
    repo.save(t)
    assert repo.get(t.table_id) == t
    assert t in repo.list_by_version(vid)


def test_context_document_save_and_get() -> None:
    repo = ContextDocumentRepository()
    wid = uuid4()
    cd = ContextDocument(
        context_document_id=uuid4(),
        workspace_id=wid,
        title="Company KPIs",
        storage_path="storage/uploads/workspaces/w/context_documents/c/raw.txt",
        created_by_user_id=uuid4(),
        created_at=NOW,
    )
    repo.save(cd)
    assert repo.get(cd.context_document_id) == cd
    assert cd in repo.list_by_workspace(wid)


def test_get_missing_returns_none() -> None:
    repo = DataSourceRepository()
    assert repo.get(uuid4()) is None
