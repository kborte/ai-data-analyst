"""Unit tests for the deterministic DataFrame profiler."""

from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from app.schemas.common import DataType, IssueType
from app.tools.data.profiler import profile_dataframe

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_FILE = FIXTURES / "simple_sales.csv"


# ---------------------------------------------------------------------------
# Basic CSV profile
# ---------------------------------------------------------------------------


def test_csv_row_count() -> None:
    df = pd.read_csv(CSV_FILE)
    cols, _ = profile_dataframe(df, "sales")
    assert all(c.total_count == 5 for c in cols)


def test_csv_column_count() -> None:
    df = pd.read_csv(CSV_FILE)
    cols, _ = profile_dataframe(df, "sales")
    assert len(cols) == 4


def test_revenue_is_numeric() -> None:
    df = pd.read_csv(CSV_FILE)
    cols, _ = profile_dataframe(df, "sales")
    rev = next(c for c in cols if c.column_name == "revenue")
    assert rev.data_type in (DataType.float_, DataType.integer)


def test_revenue_is_likely_metric() -> None:
    df = pd.read_csv(CSV_FILE)
    cols, _ = profile_dataframe(df, "sales")
    rev = next(c for c in cols if c.column_name == "revenue")
    assert rev.is_likely_metric


def test_date_column_detected() -> None:
    df = pd.read_csv(CSV_FILE)
    cols, _ = profile_dataframe(df, "sales")
    date_col = next(c for c in cols if c.column_name == "date")
    assert date_col.is_likely_date


def test_product_is_categorical() -> None:
    df = pd.read_csv(CSV_FILE)
    cols, _ = profile_dataframe(df, "sales")
    prod = next(c for c in cols if c.column_name == "product")
    assert prod.is_likely_categorical or prod.data_type == DataType.categorical


def test_no_issues_clean_csv() -> None:
    df = pd.read_csv(CSV_FILE)
    _, issues = profile_dataframe(df, "sales")
    issue_types = {i.issue_type for i in issues}
    assert IssueType.missing_values not in issue_types
    assert IssueType.duplicate_rows not in issue_types


# ---------------------------------------------------------------------------
# Missing values
# ---------------------------------------------------------------------------


def test_missing_values_issue_detected() -> None:
    df = pd.DataFrame({"revenue": [100, None, 300], "country": ["US", "UK", None]})
    _, issues = profile_dataframe(df, "t")
    assert any(i.issue_type == IssueType.missing_values for i in issues)


def test_missing_revenue_count() -> None:
    df = pd.DataFrame({"revenue": [100, None, 300, None, 500]})
    cols, issues = profile_dataframe(df, "t")
    rev_col = cols[0]
    assert rev_col.null_count == 2
    assert rev_col.null_percent == 40.0


def test_missing_revenue_high_impact() -> None:
    df = pd.DataFrame({"revenue": [100.0, None, 300.0]})
    _, issues = profile_dataframe(df, "t")
    mv = next(i for i in issues if i.issue_type == IssueType.missing_values)
    from app.schemas.common import ImpactLevel
    assert mv.impact_level == ImpactLevel.high


def test_missing_freetext_low_impact() -> None:
    # 40 rows, 20 unique (50% unique): not ID (<90%), not categorical (>15 unique),
    # not metric (string), not date → missing value should be low impact.
    values: list = [f"text_{i}" for i in range(20)] * 2 + [None]
    df = pd.DataFrame({"description": values})
    _, issues = profile_dataframe(df, "t")
    mv = next(i for i in issues if i.issue_type == IssueType.missing_values)
    from app.schemas.common import ImpactLevel
    assert mv.impact_level == ImpactLevel.low


# ---------------------------------------------------------------------------
# Duplicate rows
# ---------------------------------------------------------------------------


def test_duplicate_rows_detected() -> None:
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    _, issues = profile_dataframe(df, "t")
    assert any(i.issue_type == IssueType.duplicate_rows for i in issues)


def test_duplicate_row_count() -> None:
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    _, issues = profile_dataframe(df, "t")
    dup = next(i for i in issues if i.issue_type == IssueType.duplicate_rows)
    assert dup.affected_rows_count == 1


def test_no_duplicate_issue_when_unique() -> None:
    df = pd.DataFrame({"a": [1, 2, 3]})
    _, issues = profile_dataframe(df, "t")
    assert not any(i.issue_type == IssueType.duplicate_rows for i in issues)


# ---------------------------------------------------------------------------
# Numeric stored as text
# ---------------------------------------------------------------------------


def test_numeric_stored_as_text_detected() -> None:
    df = pd.DataFrame({"amount": ["100", "200", "300", "400", "500"]})
    _, issues = profile_dataframe(df, "t")
    assert any(i.issue_type == IssueType.numeric_stored_as_text for i in issues)


def test_numeric_stored_as_text_column_name() -> None:
    df = pd.DataFrame({"amount": ["100", "200", "300", "400", "500"]})
    _, issues = profile_dataframe(df, "t")
    issue = next(i for i in issues if i.issue_type == IssueType.numeric_stored_as_text)
    assert issue.column_name == "amount"


# ---------------------------------------------------------------------------
# Date stored as text
# ---------------------------------------------------------------------------


def test_date_stored_as_text_detected() -> None:
    df = pd.DataFrame({"event_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]})
    _, issues = profile_dataframe(df, "t")
    assert any(i.issue_type == IssueType.date_stored_as_text for i in issues)


# ---------------------------------------------------------------------------
# Excel multi-sheet
# ---------------------------------------------------------------------------


@pytest.fixture()
def two_sheet_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "multi.xlsx"
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "January"
    ws1.append(["date", "product", "revenue"])
    ws1.append(["2024-01-01", "Widget A", 500])
    ws1.append(["2024-01-02", "Widget B", 250])
    ws2 = wb.create_sheet("February")
    ws2.append(["date", "product", "revenue"])
    ws2.append(["2024-02-01", "Widget C", 720])
    wb.save(path)
    return path


def test_excel_sheet_profiled_separately(two_sheet_xlsx: Path) -> None:
    for sheet in ("January", "February"):
        df = pd.read_excel(two_sheet_xlsx, sheet_name=sheet, engine="openpyxl")
        cols, _ = profile_dataframe(df, sheet)
        assert len(cols) == 3


def test_excel_january_row_count(two_sheet_xlsx: Path) -> None:
    df = pd.read_excel(two_sheet_xlsx, sheet_name="January", engine="openpyxl")
    cols, _ = profile_dataframe(df, "January")
    assert cols[0].total_count == 2


def test_excel_no_crash(two_sheet_xlsx: Path) -> None:
    for sheet in ("January", "February"):
        df = pd.read_excel(two_sheet_xlsx, sheet_name=sheet, engine="openpyxl")
        cols, issues = profile_dataframe(df, sheet)
        assert cols
