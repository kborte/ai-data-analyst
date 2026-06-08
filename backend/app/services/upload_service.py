from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.dependencies import Repos
from app.schemas.common import (
    DatasetSourceRole,
    DatasetVersionType,
    DataSourceKind,
    UploadedFileKind,
)
from app.schemas.context_document import ContextDocument
from app.schemas.dataset import Dataset, DatasetSource, DatasetTable, DatasetVersion
from app.schemas.source import DataSource, UploadedFile
from app.schemas.uploads import ContextDocumentUploadResponse, DatasetUploadResponse, TablePreview
from app.tools.files.csv_loader import load_csv
from app.tools.files.excel_loader import load_excel
from app.tools.files.filename import make_safe_filename
from app.tools.files.storage import save_context, save_upload
from app.tools.files.text_loader import load_text

# No auth in this milestone — use a fixed system user ID.
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

TABULAR_EXTENSIONS = {".csv", ".xlsx", ".xls"}
CONTEXT_EXTENSIONS = {".txt", ".md"}

_FILE_KIND_MAP: dict[str, UploadedFileKind] = {
    ".csv": UploadedFileKind.csv,
    ".xlsx": UploadedFileKind.excel,
    ".xls": UploadedFileKind.excel,
    ".txt": UploadedFileKind.text,
    ".md": UploadedFileKind.markdown,
}


def upload_dataset(
    *,
    content: bytes,
    filename: str,
    workspace_id: UUID,
    dataset_name: str | None,
    repos: Repos,
) -> DatasetUploadResponse:
    suffix = Path(filename).suffix.lower()
    if suffix not in TABULAR_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix!r}. Expected one of {sorted(TABULAR_EXTENSIONS)}.")
    if not content:
        raise ValueError("Uploaded file is empty.")

    now = datetime.now(tz=UTC)
    ds_id, file_id, dataset_id, version_id = uuid4(), uuid4(), uuid4(), uuid4()
    safe_stem = Path(make_safe_filename(filename)).stem

    storage_path = save_upload(workspace_id, ds_id, file_id, filename, content)

    sheets = [load_csv(storage_path, table_name=safe_stem)] if suffix == ".csv" else load_excel(storage_path)
    if not sheets:
        raise ValueError("File contains no readable sheets.")

    total_rows = sum(s.total_row_count for s in sheets)

    data_source = repos.data_source.save(
        DataSource(
            data_source_id=ds_id,
            workspace_id=workspace_id,
            source_kind=DataSourceKind.uploaded_file,
            display_name=filename,
            created_by_user_id=SYSTEM_USER_ID,
            created_at=now,
        )
    )
    uploaded_file = repos.uploaded_file.save(
        UploadedFile(
            file_id=file_id,
            workspace_id=workspace_id,
            data_source_id=ds_id,
            file_kind=_FILE_KIND_MAP[suffix],
            original_filename=filename,
            storage_path=storage_path,
            size_bytes=len(content),
            uploaded_by_user_id=SYSTEM_USER_ID,
            uploaded_at=now,
        )
    )
    dataset = repos.dataset.save(
        Dataset(
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            name=dataset_name or safe_stem,
            created_by_user_id=SYSTEM_USER_ID,
            created_at=now,
        )
    )
    repos.dataset_source.save(
        DatasetSource(
            dataset_source_id=uuid4(),
            dataset_id=dataset_id,
            data_source_id=ds_id,
            role=DatasetSourceRole.primary,
        )
    )
    version = repos.dataset_version.save(
        DatasetVersion(
            dataset_version_id=version_id,
            dataset_id=dataset_id,
            version_number=1,
            version_type=DatasetVersionType.original,
            display_name="Original upload",
            row_count=total_rows,
            column_count=sheets[0].column_count,
            created_by_user_id=SYSTEM_USER_ID,
            created_at=now,
        )
    )

    tables: list[DatasetTable] = []
    previews: list[TablePreview] = []
    for sheet in sheets:
        tables.append(
            repos.dataset_table.save(
                DatasetTable(
                    table_id=uuid4(),
                    dataset_version_id=version_id,
                    table_name=sheet.table_name,
                    storage_path=storage_path,
                    row_count=sheet.total_row_count,
                    column_count=sheet.column_count,
                )
            )
        )
        previews.append(
            TablePreview(
                table_name=sheet.table_name,
                columns=sheet.columns,
                rows=sheet.preview_rows,
                total_row_count=sheet.total_row_count,
            )
        )

    return DatasetUploadResponse(
        dataset=dataset,
        data_source=data_source,
        uploaded_file=uploaded_file,
        dataset_version=version,
        dataset_tables=tables,
        previews=previews,
    )


def upload_context(
    *,
    content: bytes,
    filename: str,
    workspace_id: UUID,
    repos: Repos,
) -> ContextDocumentUploadResponse:
    suffix = Path(filename).suffix.lower()
    if suffix not in CONTEXT_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix!r}. Expected one of {sorted(CONTEXT_EXTENSIONS)}.")
    if not content:
        raise ValueError("Uploaded file is empty.")

    now = datetime.now(tz=UTC)
    ds_id, file_id, doc_id = uuid4(), uuid4(), uuid4()

    storage_path = save_context(workspace_id, doc_id, content)
    text_result = load_text(storage_path)

    data_source = repos.data_source.save(
        DataSource(
            data_source_id=ds_id,
            workspace_id=workspace_id,
            source_kind=DataSourceKind.uploaded_file,
            display_name=filename,
            created_by_user_id=SYSTEM_USER_ID,
            created_at=now,
        )
    )
    uploaded_file = repos.uploaded_file.save(
        UploadedFile(
            file_id=file_id,
            workspace_id=workspace_id,
            data_source_id=ds_id,
            file_kind=_FILE_KIND_MAP[suffix],
            original_filename=filename,
            storage_path=storage_path,
            size_bytes=len(content),
            uploaded_by_user_id=SYSTEM_USER_ID,
            uploaded_at=now,
        )
    )
    context_document = repos.context_document.save(
        ContextDocument(
            context_document_id=doc_id,
            workspace_id=workspace_id,
            data_source_id=ds_id,
            title=Path(make_safe_filename(filename)).stem,
            storage_path=storage_path,
            created_by_user_id=SYSTEM_USER_ID,
            created_at=now,
        )
    )

    return ContextDocumentUploadResponse(
        data_source=data_source,
        uploaded_file=uploaded_file,
        context_document=context_document,
        preview=text_result.preview,
        char_count=text_result.char_count,
    )
