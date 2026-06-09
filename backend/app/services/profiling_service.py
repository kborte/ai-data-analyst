"""Profiling service — M9C: read from DuckDB-backed DatasetVersion."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd

from app.dependencies import Repos
from app.schemas.profile import DataProfile
from app.tools.data.duckdb_service import get_table_info, list_tables, read_preview, temp_duckdb_path
from app.tools.data.profiler import profile_dataframe
from app.tools.files.storage_service import StorageBackend

_EXCEL_EXTS = {".xlsx", ".xls"}


def _load_table_legacy(storage_path: str, table_name: str) -> pd.DataFrame:
    """Fallback: load a table from a CSV or Excel file path (pre-M9C versions)."""
    p = Path(storage_path)
    if not p.exists():
        raise FileNotFoundError(f"Storage file not found: {storage_path}")
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p)
    if ext in _EXCEL_EXTS:
        return pd.read_excel(p, sheet_name=table_name, engine="openpyxl")
    raise ValueError(f"Unsupported file extension for profiling: {ext!r}")


def create_profiles(
    *,
    dataset_id: UUID,
    dataset_version_id: UUID,
    repos: Repos,
    storage: StorageBackend | None = None,
) -> list[DataProfile]:
    version = repos.dataset_version.get(dataset_version_id)
    if version is None or version.dataset_id != dataset_id:
        raise LookupError(
            f"DatasetVersion {dataset_version_id} not found for dataset {dataset_id}."
        )

    tables = repos.dataset_table.list_by_version(dataset_version_id)
    if not tables:
        raise LookupError(f"No tables found for DatasetVersion {dataset_version_id}.")

    now = datetime.now(tz=UTC)
    profiles: list[DataProfile] = []

    # M9C path: version has a .duckdb artifact in storage
    duckdb_path = version.storage_path
    if duckdb_path and duckdb_path.endswith(".duckdb") and storage is not None:
        with temp_duckdb_path() as tmp_db:
            db_bytes = storage.read(duckdb_path)
            tmp_db.write_bytes(db_bytes)
            for table in tables:
                df = _duckdb_table_to_dataframe(tmp_db, table.table_name)
                profiles.append(_profile_df(df, table.table_name, dataset_version_id, now, repos))
        return profiles

    # Legacy path: read each table's CSV/Excel from its own storage_path
    for table in tables:
        if not table.storage_path:
            raise ValueError(
                f"Table '{table.table_name}' has no storage path and version has no .duckdb artifact."
            )
        df = _load_table_legacy(table.storage_path, table.table_name)
        profiles.append(_profile_df(df, table.table_name, dataset_version_id, now, repos))

    return profiles


def _duckdb_table_to_dataframe(db_path: Path, table_name: str) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(f'SELECT * FROM "{table_name}"').df()  # noqa: S608
    finally:
        con.close()


def _profile_df(
    df: pd.DataFrame,
    table_name: str,
    dataset_version_id: UUID,
    now: datetime,
    repos: Repos,
) -> DataProfile:
    col_profiles, issues = profile_dataframe(df, table_name)
    return repos.profile.save(
        DataProfile(
            profile_id=uuid4(),
            dataset_version_id=dataset_version_id,
            table_name=table_name,
            row_count=len(df),
            column_count=len(df.columns),
            column_profiles=col_profiles,
            quality_issues=issues,
            likely_id_columns=[c.column_name for c in col_profiles if c.is_likely_id],
            likely_metric_columns=[c.column_name for c in col_profiles if c.is_likely_metric],
            likely_categorical_columns=[c.column_name for c in col_profiles if c.is_likely_categorical],
            likely_date_columns=[c.column_name for c in col_profiles if c.is_likely_date],
            created_at=now,
        )
    )
