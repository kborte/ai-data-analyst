"""Tests for DuckDB version artifact utilities (M9B)."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

from app.tools.data.duckdb_service import (
    TableInfo,
    copy_version,
    create_version_duckdb,
    from_csv_bytes,
    from_excel_bytes,
    get_table_info,
    list_tables,
    make_unique_table_names,
    read_preview,
    sanitize_table_name,
    temp_duckdb_path,
)


# ---------------------------------------------------------------------------
# sanitize_table_name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("sales", "sales"),
    ("My Table!", "my_table"),
    ("  Revenue  ", "revenue"),
    ("123start", "t_123start"),
    ("Q1-Revenue (USD)", "q1_revenue_usd"),
    ("___", "table"),
    ("", "table"),
    ("a__b__c", "a_b_c"),
    ("UPPER_CASE", "upper_case"),
])
def test_sanitize_table_name(raw: str, expected: str) -> None:
    assert sanitize_table_name(raw) == expected


# ---------------------------------------------------------------------------
# make_unique_table_names
# ---------------------------------------------------------------------------

def test_make_unique_table_names_no_duplicates() -> None:
    assert make_unique_table_names(["sales", "revenue"]) == ["sales", "revenue"]


def test_make_unique_table_names_duplicates() -> None:
    result = make_unique_table_names(["Sales", "sales", "Sales"])
    assert result == ["sales", "sales_1", "sales_2"]


def test_make_unique_table_names_sanitizes_first() -> None:
    result = make_unique_table_names(["My Table", "my_table"])
    assert result == ["my_table", "my_table_1"]


# ---------------------------------------------------------------------------
# create_version_duckdb
# ---------------------------------------------------------------------------

def test_create_version_duckdb_single_table(tmp_path: Path) -> None:
    db = tmp_path / "v1.duckdb"
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    create_version_duckdb({"test": df}, db)
    assert db.exists()
    assert list_tables(db) == ["test"]


def test_create_version_duckdb_multiple_tables(tmp_path: Path) -> None:
    db = tmp_path / "v1.duckdb"
    df1 = pd.DataFrame({"x": [1]})
    df2 = pd.DataFrame({"y": [2]})
    create_version_duckdb({"orders": df1, "products": df2}, db)
    assert sorted(list_tables(db)) == ["orders", "products"]


def test_create_version_duckdb_raises_if_exists(tmp_path: Path) -> None:
    db = tmp_path / "v1.duckdb"
    df = pd.DataFrame({"a": [1]})
    create_version_duckdb({"t": df}, db)
    with pytest.raises(FileExistsError):
        create_version_duckdb({"t": df}, db)


def test_create_version_duckdb_creates_parent_dirs(tmp_path: Path) -> None:
    db = tmp_path / "deep" / "nested" / "v1.duckdb"
    create_version_duckdb({"t": pd.DataFrame({"a": [1]})}, db)
    assert db.exists()


# ---------------------------------------------------------------------------
# from_csv_bytes
# ---------------------------------------------------------------------------

def test_from_csv_bytes(tmp_path: Path) -> None:
    csv = b"name,age\nAlice,30\nBob,25\n"
    db = tmp_path / "v1.duckdb"
    from_csv_bytes(csv, "My CSV!", db)
    assert list_tables(db) == ["my_csv"]
    info = get_table_info(db, "my_csv")
    assert info.row_count == 2
    assert info.column_count == 2


# ---------------------------------------------------------------------------
# from_excel_bytes
# ---------------------------------------------------------------------------

def _make_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet, index=False)
    return buf.getvalue()


def test_from_excel_bytes_single_sheet(tmp_path: Path) -> None:
    data = _make_excel({"Sales Data": pd.DataFrame({"rev": [100, 200]})})
    db = tmp_path / "v1.duckdb"
    from_excel_bytes(data, db)
    assert list_tables(db) == ["sales_data"]


def test_from_excel_bytes_multiple_sheets(tmp_path: Path) -> None:
    data = _make_excel({
        "Orders": pd.DataFrame({"id": [1]}),
        "Products": pd.DataFrame({"sku": ["A"]}),
    })
    db = tmp_path / "v1.duckdb"
    from_excel_bytes(data, db)
    assert sorted(list_tables(db)) == ["orders", "products"]


def test_from_excel_bytes_skips_empty_sheets(tmp_path: Path) -> None:
    data = _make_excel({
        "Real": pd.DataFrame({"v": [1]}),
        "Empty": pd.DataFrame(),
    })
    db = tmp_path / "v1.duckdb"
    from_excel_bytes(data, db)
    assert list_tables(db) == ["real"]


def test_from_excel_bytes_deduplicates_sheet_names(tmp_path: Path) -> None:
    data = _make_excel({
        "Sheet": pd.DataFrame({"a": [1]}),
        "Sheet ": pd.DataFrame({"b": [2]}),
    })
    db = tmp_path / "v1.duckdb"
    from_excel_bytes(data, db)
    tables = list_tables(db)
    assert len(tables) == 2
    assert len(set(tables)) == 2  # all unique


def test_from_excel_bytes_raises_all_empty(tmp_path: Path) -> None:
    data = _make_excel({"Empty": pd.DataFrame()})
    with pytest.raises(ValueError, match="no non-empty"):
        from_excel_bytes(data, tmp_path / "v1.duckdb")


def test_from_excel_bytes_subset_sheets(tmp_path: Path) -> None:
    data = _make_excel({
        "A": pd.DataFrame({"x": [1]}),
        "B": pd.DataFrame({"y": [2]}),
    })
    db = tmp_path / "v1.duckdb"
    from_excel_bytes(data, db, sheet_names=["A"])
    assert list_tables(db) == ["a"]


# ---------------------------------------------------------------------------
# list_tables / get_table_info
# ---------------------------------------------------------------------------

def test_get_table_info(tmp_path: Path) -> None:
    db = tmp_path / "v1.duckdb"
    df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
    create_version_duckdb({"data": df}, db)
    info = get_table_info(db, "data")
    assert isinstance(info, TableInfo)
    assert info.row_count == 3
    assert info.column_count == 2
    assert info.columns == ["col1", "col2"]
    assert info.table_name == "data"


# ---------------------------------------------------------------------------
# read_preview
# ---------------------------------------------------------------------------

def test_read_preview_returns_dicts(tmp_path: Path) -> None:
    db = tmp_path / "v1.duckdb"
    df = pd.DataFrame({"x": range(20)})
    create_version_duckdb({"nums": df}, db)
    rows = read_preview(db, "nums", limit=5)
    assert len(rows) == 5
    assert all(isinstance(r, dict) for r in rows)
    assert rows[0]["x"] == 0


def test_read_preview_respects_limit(tmp_path: Path) -> None:
    db = tmp_path / "v1.duckdb"
    create_version_duckdb({"t": pd.DataFrame({"v": range(50)})}, db)
    assert len(read_preview(db, "t", limit=10)) == 10
    assert len(read_preview(db, "t", limit=100)) == 50  # only 50 rows exist


# ---------------------------------------------------------------------------
# copy_version
# ---------------------------------------------------------------------------

def test_copy_version(tmp_path: Path) -> None:
    src = tmp_path / "v1.duckdb"
    dest = tmp_path / "v2.duckdb"
    create_version_duckdb({"data": pd.DataFrame({"a": [1, 2]})}, src)
    copy_version(src, dest)
    assert dest.exists()
    assert list_tables(dest) == ["data"]


def test_copy_version_raises_if_dest_exists(tmp_path: Path) -> None:
    src = tmp_path / "v1.duckdb"
    dest = tmp_path / "v2.duckdb"
    df = pd.DataFrame({"a": [1]})
    create_version_duckdb({"t": df}, src)
    create_version_duckdb({"t": df}, dest)
    with pytest.raises(FileExistsError):
        copy_version(src, dest)


def test_copy_version_creates_parent_dirs(tmp_path: Path) -> None:
    src = tmp_path / "v1.duckdb"
    dest = tmp_path / "sub" / "dir" / "v2.duckdb"
    create_version_duckdb({"t": pd.DataFrame({"a": [1]})}, src)
    copy_version(src, dest)
    assert dest.exists()


def test_copy_is_independent(tmp_path: Path) -> None:
    """Writing to dest after copy must not affect src (immutability check)."""
    import duckdb as _duckdb

    src = tmp_path / "v1.duckdb"
    dest = tmp_path / "v2.duckdb"
    create_version_duckdb({"t": pd.DataFrame({"a": [1]})}, src)
    copy_version(src, dest)

    con = _duckdb.connect(str(dest))
    con.execute('INSERT INTO "t" VALUES (99)')
    con.close()

    assert get_table_info(src, "t").row_count == 1
    assert get_table_info(dest, "t").row_count == 2


# ---------------------------------------------------------------------------
# temp_duckdb_path
# ---------------------------------------------------------------------------

def test_temp_duckdb_path_cleaned_on_success() -> None:
    with temp_duckdb_path() as p:
        create_version_duckdb({"t": pd.DataFrame({"a": [1]})}, p)
        assert p.exists()
        parent = p.parent
    assert not parent.exists()


def test_temp_duckdb_path_cleaned_on_exception() -> None:
    parent = None
    with pytest.raises(RuntimeError):
        with temp_duckdb_path() as p:
            parent = p.parent
            create_version_duckdb({"t": pd.DataFrame({"a": [1]})}, p)
            raise RuntimeError("boom")
    assert parent is not None and not parent.exists()


def test_temp_duckdb_path_does_not_exist_on_entry() -> None:
    with temp_duckdb_path() as p:
        assert not p.exists()
