from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SheetInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sheet_name: str
    row_count: int
    column_count: int


class ColumnInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    type: str
    nullable: bool
    unique_count: int
    null_count: int
    sample_values: list[Any] = []
    stats: dict[str, Any] = {}


class ColumnsResponse(BaseModel):
    dataset_id: UUID
    columns: list[ColumnInfo]


class DatasetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    original_filename: str
    file_type: str
    file_size: int
    row_count: int
    column_count: int
    status: str
    created_at: datetime
    updated_at: datetime


class DatasetDetail(DatasetSummary):
    error_message: str | None = None
    columns: list[ColumnInfo] = []
    sheets: list[SheetInfo] = []


class DatasetPreview(BaseModel):
    dataset_id: UUID
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    page: int
    page_size: int
