from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd

from app.dependencies import Repos
from app.schemas.profile import DataProfile
from app.tools.data.profiler import profile_dataframe

_EXCEL_EXTS = {".xlsx", ".xls"}


def _load_table(storage_path: str, table_name: str) -> pd.DataFrame:
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
) -> list[DataProfile]:
    version = repos.dataset_version.get(dataset_version_id)
    if version is None or version.dataset_id != dataset_id:
        raise LookupError(f"DatasetVersion {dataset_version_id} not found for dataset {dataset_id}.")

    tables = repos.dataset_table.list_by_version(dataset_version_id)
    if not tables:
        raise LookupError(f"No tables found for DatasetVersion {dataset_version_id}.")

    profiles: list[DataProfile] = []
    now = datetime.now(tz=UTC)

    for table in tables:
        if not table.storage_path:
            raise ValueError(f"Table '{table.table_name}' has no storage path.")
        df = _load_table(table.storage_path, table.table_name)
        col_profiles, issues = profile_dataframe(df, table.table_name)

        profile = repos.profile.save(
            DataProfile(
                profile_id=uuid4(),
                dataset_version_id=dataset_version_id,
                table_name=table.table_name,
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
        profiles.append(profile)

    return profiles
