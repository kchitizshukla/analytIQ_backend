from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ProfileRequest(BaseModel):
    dataset_id: UUID


class ColumnProfile(BaseModel):
    name: str
    type: str
    null_count: int
    null_percentage: float
    unique_count: int
    # numeric-only fields are optional
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    p25: float | None = None
    p75: float | None = None
    outlier_count: int | None = None
    top_values: list[dict[str, Any]] | None = None


class DataProfile(BaseModel):
    dataset_id: UUID
    row_count: int
    column_count: int
    missing_values: int
    missing_percentage: float
    duplicate_rows: int
    numeric_columns: list[str]
    categorical_columns: list[str]
    datetime_columns: list[str]
    completeness: float
    quality_score: float
    columns: list[ColumnProfile]


class StatisticsRequest(BaseModel):
    dataset_id: UUID
    columns: list[str] | None = None


class StatisticsResult(BaseModel):
    dataset_id: UUID
    statistics: dict[str, dict[str, Any]]
    correlations: dict[str, dict[str, float]] | None = None
