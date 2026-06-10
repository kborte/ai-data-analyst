"""Upload service — M9C: raw uploads and .duckdb version artifacts via StorageBackend."""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

import pandas as pd

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
from app.tools.data.duckdb_service import (
    TableInfo,
    create_version_duckdb,
    get_table_info,
    list_tables,
    make_unique_table_names,
    read_preview,
    temp_duckdb_path,
)
from app.tools.files.filename import make_safe_filename
from app.tools.files.storage_service import StorageBackend, raw_upload_path, version_path
from app.tools.files.text_loader import load_text

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

_PREVIEW_LIMIT = 100
_MIN_DATE_PARSE_RATIO = 0.5


def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce object columns to types DuckDB can ingest without crashing.

    - Whitespace-only strings → NaN.
    - String columns where ≥50% of non-null values parse as dates → datetime64.
      This handles non-ISO formats like MM-DD-YYYY that DuckDB cannot cast.
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype != object:
            continue
        # Whitespace-only → NaN
        df[col] = df[col].replace(r"^\s*$", float("nan"), regex=True)
        # Try datetime parse; keep only if majority of non-null values succeed
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        parsed = pd.to_datetime(non_null, errors="coerce")
        if parsed.notna().sum() / len(non_null) >= _MIN_DATE_PARSE_RATIO:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Internal parsing helpers (bytes → DataFrames + preview metadata)
# ---------------------------------------------------------------------------

def _dataclasses_from_bytes(
    content: bytes, suffix: str, stem: str
) -> list[tuple[str, pd.DataFrame, list[dict[str, Any]]]]:
    """Return [(sanitized_table_name, df, preview_rows), ...] for CSV or Excel."""
    if suffix == ".csv":
        df = _sanitize_df(pd.read_csv(io.BytesIO(content)))
        preview = df.head(_PREVIEW_LIMIT).where(pd.notnull(df), None).to_dict(orient="records")
        return [(stem, df, preview)]

    xls = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
    raw: list[tuple[str, pd.DataFrame]] = []
    for sheet in xls.sheet_names:
        df = xls.parse(sheet)
        if not df.empty:
            raw.append((sheet, df))
    if not raw:
        raise ValueError("Excel file contains no non-empty sheets.")

    safe_names = make_unique_table_names([name for name, _ in raw])
    result = []
    for safe_name, (_, df) in zip(safe_names, raw):
        df = _sanitize_df(df)
        preview = df.head(_PREVIEW_LIMIT).where(pd.notnull(df), None).to_dict(orient="records")
        result.append((safe_name, df, preview))
    return result


# ---------------------------------------------------------------------------
# Public upload functions
# ---------------------------------------------------------------------------

def upload_dataset(
    *,
    content: bytes,
    filename: str,
    workspace_id: UUID,
    dataset_name: str | None,
    repos: Repos,
    storage: StorageBackend,
    existing_dataset_id: UUID | None = None,
) -> DatasetUploadResponse:
    suffix = Path(filename).suffix.lower()
    if suffix not in TABULAR_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {suffix!r}. Expected one of {sorted(TABULAR_EXTENSIONS)}."
        )
    if not content:
        raise ValueError("Uploaded file is empty.")

    now = datetime.now(tz=UTC)
    ds_id = uuid4()
    file_id = uuid4()
    version_id = uuid4()
    safe_stem = Path(make_safe_filename(filename)).stem

    # --- Parse bytes to DataFrames ---
    tables_data = _dataclasses_from_bytes(content, suffix, safe_stem)
    if not tables_data:
        raise ValueError("File contains no readable tables.")

    # --- Resolve or create Dataset ---
    if existing_dataset_id is not None:
        dataset = repos.dataset.get(existing_dataset_id)
        if dataset is None or dataset.workspace_id != workspace_id:
            raise ValueError(f"Dataset {existing_dataset_id} not found in workspace {workspace_id}.")
        dataset_id = existing_dataset_id
        existing_versions = repos.dataset_version.list_by_dataset(dataset_id)
        next_version_number = max((v.version_number for v in existing_versions), default=0) + 1
        new_dataset = False
    else:
        dataset_id = uuid4()
        dataset = repos.dataset.save(
            Dataset(
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                name=dataset_name or safe_stem,
                created_by_user_id=SYSTEM_USER_ID,
                created_at=now,
            )
        )
        next_version_number = 1
        new_dataset = True

    # --- Save raw upload to storage ---
    raw_path = raw_upload_path(workspace_id, dataset_id, file_id, filename)
    storage.save(raw_path, content)

    # --- Build .duckdb version artifact ---
    duckdb_tables = {name: df for name, df, _ in tables_data}
    ver_storage_path = version_path(workspace_id, dataset_id, next_version_number, "original")

    with temp_duckdb_path() as tmp_db:
        create_version_duckdb(duckdb_tables, tmp_db)
        duckdb_bytes = tmp_db.read_bytes()

    storage.save(ver_storage_path, duckdb_bytes)

    # --- Persist metadata (all in one transaction via get_db()) ---
    # Storage writes above are outside the Postgres transaction.
    # If any metadata write fails, get_db() rolls back all DB flushes atomically.
    # The storage artifacts then become orphaned — best-effort cleanup is attempted below.
    try:
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
                storage_path=raw_path,
                size_bytes=len(content),
                uploaded_by_user_id=SYSTEM_USER_ID,
                uploaded_at=now,
            )
        )
        if new_dataset:
            repos.dataset_source.save(
                DatasetSource(
                    dataset_source_id=uuid4(),
                    dataset_id=dataset_id,
                    data_source_id=ds_id,
                    role=DatasetSourceRole.primary,
                )
            )
        else:
            repos.dataset_source.save(
                DatasetSource(
                    dataset_source_id=uuid4(),
                    dataset_id=dataset_id,
                    data_source_id=ds_id,
                    role=DatasetSourceRole.supplementary,
                )
            )

        total_rows = sum(len(df) for _, df, _ in tables_data)
        version = repos.dataset_version.save(
            DatasetVersion(
                dataset_version_id=version_id,
                dataset_id=dataset_id,
                version_number=next_version_number,
                version_type=DatasetVersionType.original,
                display_name="Original upload" if next_version_number == 1 else f"Upload v{next_version_number}",
                storage_path=ver_storage_path,
                row_count=total_rows,
                column_count=tables_data[0][1].shape[1],
                created_by_user_id=SYSTEM_USER_ID,
                created_at=now,
            )
        )

        db_tables: list[DatasetTable] = []
        previews: list[TablePreview] = []
        for table_name, df, preview_rows in tables_data:
            # storage_path is None — the table lives inside the version's .duckdb artifact
            db_tables.append(
                repos.dataset_table.save(
                    DatasetTable(
                        table_id=uuid4(),
                        dataset_version_id=version_id,
                        table_name=table_name,
                        storage_path=None,
                        row_count=len(df),
                        column_count=df.shape[1],
                    )
                )
            )
            previews.append(
                TablePreview(
                    table_name=table_name,
                    columns=list(df.columns),
                    rows=preview_rows,
                    total_row_count=len(df),
                )
            )
    except Exception:
        # Best-effort: clean up orphaned storage artifacts. Cleanup failures must not
        # hide the original DB error.
        for orphan_path in (raw_path, ver_storage_path):
            try:
                storage.delete(orphan_path)
            except Exception:
                logger.warning("storage cleanup failed for orphaned artifact: %s", orphan_path)
        raise

    return DatasetUploadResponse(
        dataset=dataset,
        data_source=data_source,
        uploaded_file=uploaded_file,
        dataset_version=version,
        dataset_tables=db_tables,
        previews=previews,
    )


def upload_context(
    *,
    content: bytes,
    filename: str,
    workspace_id: UUID,
    repos: Repos,
    storage: StorageBackend,
) -> ContextDocumentUploadResponse:
    suffix = Path(filename).suffix.lower()
    if suffix not in CONTEXT_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {suffix!r}. Expected one of {sorted(CONTEXT_EXTENSIONS)}."
        )
    if not content:
        raise ValueError("Uploaded file is empty.")

    from app.tools.files.storage_service import result_path  # local import to avoid circular

    now = datetime.now(tz=UTC)
    ds_id = uuid4()
    file_id = uuid4()
    doc_id = uuid4()

    # Use a simple storage path for context documents (workspace-scoped)
    ctx_path = f"workspaces/{workspace_id}/context_documents/{doc_id}/raw.txt"
    storage.save(ctx_path, content)

    # Parse text for preview using in-memory approach
    text_content = content.decode("utf-8", errors="replace")
    char_count = len(text_content)
    preview = text_content[:500]

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
            storage_path=ctx_path,
            size_bytes=len(content),
            uploaded_by_user_id=SYSTEM_USER_ID,
            uploaded_at=now,
        )
    )
    safe_stem = Path(make_safe_filename(filename)).stem
    context_document = repos.context_document.save(
        ContextDocument(
            context_document_id=doc_id,
            workspace_id=workspace_id,
            data_source_id=ds_id,
            title=safe_stem,
            storage_path=ctx_path,
            created_by_user_id=SYSTEM_USER_ID,
            created_at=now,
        )
    )

    return ContextDocumentUploadResponse(
        data_source=data_source,
        uploaded_file=uploaded_file,
        context_document=context_document,
        preview=preview,
        char_count=char_count,
    )
