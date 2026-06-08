from typing import Any

from pydantic import BaseModel

from app.schemas.context_document import ContextDocument
from app.schemas.dataset import Dataset, DatasetTable, DatasetVersion
from app.schemas.source import DataSource, UploadedFile


class TablePreview(BaseModel):
    table_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total_row_count: int


class DatasetUploadResponse(BaseModel):
    dataset: Dataset
    data_source: DataSource
    uploaded_file: UploadedFile
    dataset_version: DatasetVersion
    dataset_tables: list[DatasetTable]
    previews: list[TablePreview]


class ContextDocumentUploadResponse(BaseModel):
    data_source: DataSource
    uploaded_file: UploadedFile
    context_document: ContextDocument
    preview: str
    char_count: int
