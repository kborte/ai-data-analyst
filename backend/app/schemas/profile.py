from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DataType, ImpactLevel, IssueType


class NumericSummary(BaseModel):
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    q1: float | None = None
    q3: float | None = None


class DateSummary(BaseModel):
    min_date: str | None = None
    max_date: str | None = None
    n_unique: int | None = None


class ColumnProfile(BaseModel):
    column_name: str
    data_type: DataType
    total_count: int
    null_count: int
    null_percent: float
    unique_count: int
    unique_percent: float
    top_values: list[Any] = []
    numeric_summary: NumericSummary | None = None
    date_summary: DateSummary | None = None
    is_likely_id: bool = False
    is_likely_metric: bool = False
    is_likely_categorical: bool = False
    is_likely_date: bool = False


class DataQualityIssue(BaseModel):
    issue_type: IssueType
    table_name: str
    column_name: str | None = None
    description: str
    affected_rows_count: int
    affected_rows_percent: float
    impact_level: ImpactLevel
    sample_values: list[Any] = []


class DataProfile(BaseModel):
    profile_id: UUID
    dataset_version_id: UUID
    table_name: str
    row_count: int
    column_count: int
    column_profiles: list[ColumnProfile]
    quality_issues: list[DataQualityIssue] = []
    likely_id_columns: list[str] = []
    likely_metric_columns: list[str] = []
    likely_categorical_columns: list[str] = []
    likely_date_columns: list[str] = []
    created_at: datetime
    metadata: dict[str, Any] = {}
