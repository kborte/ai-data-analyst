from app.tools.files.filename import make_safe_filename


def test_spaces_replaced() -> None:
    assert make_safe_filename("May Sales Report.xlsx") == "May_Sales_Report.xlsx"


def test_path_traversal_stripped() -> None:
    assert make_safe_filename("../../sales.csv") == "sales.csv"


def test_absolute_path_stripped() -> None:
    assert make_safe_filename("/etc/passwd") == "passwd"


def test_backslash_path_stripped() -> None:
    assert make_safe_filename("..\\..\\evil.csv") == "evil.csv"


def test_extension_preserved() -> None:
    result = make_safe_filename("report.xlsx")
    assert result.endswith(".xlsx")


def test_no_extension() -> None:
    result = make_safe_filename("notes")
    assert result == "notes"


def test_special_chars_replaced() -> None:
    result = make_safe_filename("my file (v2)!.csv")
    assert " " not in result
    assert "(" not in result
    assert result.endswith(".csv")


def test_empty_stem_fallback() -> None:
    result = make_safe_filename("....csv")
    assert result.endswith(".csv")
    assert len(result) > len(".csv")
