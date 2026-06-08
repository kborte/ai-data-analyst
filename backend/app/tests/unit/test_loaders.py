from pathlib import Path

import openpyxl
import pytest

from app.tools.files.csv_loader import load_csv
from app.tools.files.excel_loader import load_excel
from app.tools.files.filename import make_safe_filename
from app.tools.files.text_loader import load_text

FIXTURES = Path(__file__).parent.parent / "fixtures"
CSV_FILE = FIXTURES / "simple_sales.csv"
TXT_FILE = FIXTURES / "company_context.txt"


# ---------------------------------------------------------------------------
# Filename safety
# ---------------------------------------------------------------------------


def test_filename_path_traversal() -> None:
    assert make_safe_filename("../../sales.csv") == "sales.csv"


def test_filename_spaces() -> None:
    assert make_safe_filename("May Sales Report.xlsx") == "May_Sales_Report.xlsx"


def test_filename_preserves_extension() -> None:
    assert make_safe_filename("data file.csv").endswith(".csv")


def test_filename_absolute_path() -> None:
    assert "/" not in make_safe_filename("/etc/passwd")


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------


def test_csv_columns() -> None:
    result = load_csv(CSV_FILE)
    assert result.columns == ["date", "product", "units", "revenue"]


def test_csv_row_count() -> None:
    result = load_csv(CSV_FILE)
    assert result.total_row_count == 5


def test_csv_column_count() -> None:
    result = load_csv(CSV_FILE)
    assert result.column_count == 4


def test_csv_preview_rows_returned() -> None:
    result = load_csv(CSV_FILE)
    assert len(result.preview_rows) == 5
    assert result.preview_rows[0]["product"] == "Widget A"


def test_csv_table_name_defaults_to_stem() -> None:
    result = load_csv(CSV_FILE)
    assert result.table_name == "simple_sales"


def test_csv_custom_table_name() -> None:
    result = load_csv(CSV_FILE, table_name="sales_jan")
    assert result.table_name == "sales_jan"


# ---------------------------------------------------------------------------
# Excel loader — fixture generated in-test (avoids committing binary)
# ---------------------------------------------------------------------------


@pytest.fixture()
def multi_sheet_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "multi_sheet_sales.xlsx"
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


def test_excel_sheet_count(multi_sheet_xlsx: Path) -> None:
    results = load_excel(multi_sheet_xlsx)
    assert len(results) == 2


def test_excel_sheet_names(multi_sheet_xlsx: Path) -> None:
    results = load_excel(multi_sheet_xlsx)
    names = [r.table_name for r in results]
    assert "January" in names
    assert "February" in names


def test_excel_january_rows(multi_sheet_xlsx: Path) -> None:
    results = load_excel(multi_sheet_xlsx)
    jan = next(r for r in results if r.table_name == "January")
    assert jan.total_row_count == 2
    assert jan.column_count == 3
    assert jan.preview_rows[0]["product"] == "Widget A"


def test_excel_february_rows(multi_sheet_xlsx: Path) -> None:
    results = load_excel(multi_sheet_xlsx)
    feb = next(r for r in results if r.table_name == "February")
    assert feb.total_row_count == 1
    assert feb.preview_rows[0]["revenue"] == 720


# ---------------------------------------------------------------------------
# Text loader
# ---------------------------------------------------------------------------


def test_text_content_loaded() -> None:
    result = load_text(TXT_FILE)
    assert "Acme Corp" in result.content


def test_text_preview_truncated() -> None:
    result = load_text(TXT_FILE)
    assert len(result.preview) <= 500


def test_text_char_count() -> None:
    result = load_text(TXT_FILE)
    assert result.char_count == len(result.content)


def test_text_line_count() -> None:
    result = load_text(TXT_FILE)
    assert result.line_count >= 1


def test_text_unsupported_extension(tmp_path: Path) -> None:
    bad = tmp_path / "data.pdf"
    bad.write_text("content")
    with pytest.raises(ValueError, match="Unsupported"):
        load_text(bad)
