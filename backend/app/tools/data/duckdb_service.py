"""
DuckDB utilities for dataset version artifacts (M9B).

One .duckdb file = one materialized DatasetVersion.
Existing version files are immutable — never opened with write intent after creation.

Temp-file discipline: callers use temp_duckdb_path() to get a scratch path that is
deleted on context-manager exit even if an exception occurs.
"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

import duckdb
import pandas as pd


# ---------------------------------------------------------------------------
# Table naming
# ---------------------------------------------------------------------------

_SAFE_RE = re.compile(r"[^a-z0-9_]")
_LEADING_DIGIT_RE = re.compile(r"^[0-9]")


def sanitize_table_name(name: str) -> str:
    """Return a safe DuckDB table identifier derived from *name*.

    Rules applied in order:
    1. Strip whitespace, lower-case.
    2. Replace any char that isn't [a-z0-9_] with '_'.
    3. Collapse consecutive underscores.
    4. Strip leading/trailing underscores.
    5. Prefix 't_' if the result starts with a digit.
    6. Fall back to 'table' if the result is empty.
    """
    s = name.strip().lower()
    s = _SAFE_RE.sub("_", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    if _LEADING_DIGIT_RE.match(s):
        s = "t_" + s
    return s or "table"


def make_unique_table_names(names: list[str]) -> list[str]:
    """Sanitize *names* and resolve duplicates by appending _1, _2, …"""
    sanitized = [sanitize_table_name(n) for n in names]
    seen: dict[str, int] = {}
    result: list[str] = []
    for name in sanitized:
        if name not in seen:
            seen[name] = 0
            result.append(name)
        else:
            seen[name] += 1
            result.append(f"{name}_{seen[name]}")
    return result


# ---------------------------------------------------------------------------
# TableInfo
# ---------------------------------------------------------------------------

@dataclass
class TableInfo:
    table_name: str
    row_count: int
    column_count: int
    columns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core creation
# ---------------------------------------------------------------------------

def create_version_duckdb(tables: dict[str, pd.DataFrame], path: Path) -> None:
    """Write *tables* into a new .duckdb file at *path*.

    *path* must not already exist (version files are immutable after creation).
    Table names in *tables* are assumed to be already sanitized.

    Raises FileExistsError if *path* exists.
    """
    if path.exists():
        raise FileExistsError(f"Version file already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        for table_name, df in tables.items():
            con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM df')  # noqa: S608
    finally:
        con.close()


def from_csv_bytes(data: bytes, table_name: str, path: Path) -> None:
    """Create a single-table .duckdb version file from CSV *data*.

    *table_name* is sanitized internally.
    """
    safe_name = sanitize_table_name(table_name)
    df = pd.read_csv(io.BytesIO(data))
    create_version_duckdb({safe_name: df}, path)


def from_excel_bytes(data: bytes, path: Path, sheet_names: list[str] | None = None) -> None:
    """Create a multi-table .duckdb version file from Excel *data*.

    Each non-empty sheet becomes one table.  Sheet names are sanitized and
    deduplicated.  If *sheet_names* is provided, only those sheets are included.
    """
    xls = pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
    sheets = sheet_names if sheet_names is not None else xls.sheet_names
    raw_frames: dict[str, pd.DataFrame] = {}
    for sheet in sheets:
        df = xls.parse(sheet)
        if df.empty:
            continue
        raw_frames[sheet] = df

    if not raw_frames:
        raise ValueError("Excel file contains no non-empty sheets")

    unique_names = make_unique_table_names(list(raw_frames.keys()))
    tables = dict(zip(unique_names, raw_frames.values()))
    create_version_duckdb(tables, path)


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

def list_tables(path: Path) -> list[str]:
    """Return table names stored in the .duckdb file at *path*."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = con.execute("SHOW TABLES").fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


def get_table_info(path: Path, table_name: str) -> TableInfo:
    """Return row/column counts and column names for *table_name*."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        row_count: int = con.execute(
            f'SELECT COUNT(*) FROM "{table_name}"'  # noqa: S608
        ).fetchone()[0]
        cols = con.execute(f'DESCRIBE "{table_name}"').fetchall()  # noqa: S608
        column_names = [c[0] for c in cols]
        return TableInfo(
            table_name=table_name,
            row_count=row_count,
            column_count=len(column_names),
            columns=column_names,
        )
    finally:
        con.close()


def read_preview(path: Path, table_name: str, limit: int = 100) -> list[dict]:
    """Return up to *limit* rows from *table_name* as a list of dicts."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        df = con.execute(
            f'SELECT * FROM "{table_name}" LIMIT {int(limit)}'  # noqa: S608
        ).df()
        return df.to_dict(orient="records")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Versioning helpers
# ---------------------------------------------------------------------------

def copy_version(src: Path, dest: Path) -> None:
    """Copy an immutable version file to *dest* to use as a new version base.

    *dest* must not already exist.
    """
    if dest.exists():
        raise FileExistsError(f"Destination version file already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


# ---------------------------------------------------------------------------
# Temp-file context manager
# ---------------------------------------------------------------------------

@contextmanager
def temp_duckdb_path(suffix: str = ".duckdb") -> Generator[Path, None, None]:
    """Yield a temporary Path for a scratch .duckdb file.

    The file (and its parent temp directory) is deleted on exit, even if an
    exception is raised.  The path does not exist when yielded — DuckDB will
    create it on first connect.
    """
    tmp_dir = tempfile.mkdtemp(prefix="duckdb_scratch_")
    try:
        yield Path(tmp_dir) / f"scratch{suffix}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
