from pathlib import Path
from typing import Any

import pandas as pd

from app.tools.files.csv_loader import PREVIEW_ROW_LIMIT, TabularSheetResult


def load_excel(path: Path | str) -> list[TabularSheetResult]:
    """
    Read all sheets from an Excel workbook.
    Returns one TabularSheetResult per sheet.
    """
    xl = pd.ExcelFile(path, engine="openpyxl")
    results: list[TabularSheetResult] = []
    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name)
        preview: list[dict[str, Any]] = (
            df.head(PREVIEW_ROW_LIMIT).where(pd.notnull(df), None).to_dict(orient="records")
        )
        results.append(
            TabularSheetResult(
                table_name=sheet_name,
                columns=list(df.columns),
                preview_rows=preview,
                total_row_count=len(df),
                column_count=len(df.columns),
            )
        )
    return results
