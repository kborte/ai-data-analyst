from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class TabularSheetResult:
    table_name: str
    columns: list[str]
    preview_rows: list[dict[str, Any]]
    total_row_count: int
    column_count: int


PREVIEW_ROW_LIMIT = 20


def load_csv(path: Path | str, table_name: str | None = None) -> TabularSheetResult:
    """
    Read a CSV file and return column names, preview rows, and counts.
    Does not materialise to Parquet — parse on demand for preview.
    """
    df = pd.read_csv(path, nrows=None)
    name = table_name or Path(path).stem
    preview = df.head(PREVIEW_ROW_LIMIT).where(pd.notnull(df), None).to_dict(orient="records")
    return TabularSheetResult(
        table_name=name,
        columns=list(df.columns),
        preview_rows=preview,
        total_row_count=len(df),
        column_count=len(df.columns),
    )
