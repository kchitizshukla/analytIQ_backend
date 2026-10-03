from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

CHART_TYPES = {"bar", "grouped_bar", "line", "area", "pie", "scatter", "histogram", "table"}
AGGREGATIONS = {"sum", "mean", "avg", "count", "min", "max", "median"}


class FilterClause(BaseModel):
    column: str
    op: str = "eq"  # eq, ne, gt, gte, lt, lte, in, contains
    value: Any = None


class VisualizationConfig(BaseModel):
    dataset_id: UUID
    chart_type: str = "bar"
    dimension: str | None = None          # X-axis / category
    measures: list[str] = Field(default_factory=list)
    group_by: str | None = None
    aggregation: dict[str, str] = Field(default_factory=dict)
    default_aggregation: str = "sum"
    filters: list[FilterClause] = Field(default_factory=list)
    limit: int | None = 100
    sort: str | None = None               # 'asc' | 'desc'
    title: str | None = None


class SeriesData(BaseModel):
    name: str
    data: list[Any]


class VisualizationResult(BaseModel):
    dataset_id: UUID
    chart_type: str
    title: str
    dimension: str | None = None
    measures: list[str] = []
    categories: list[Any] = []            # x-axis labels
    series: list[SeriesData] = []         # one entry per measure/group
    rows: list[dict[str, Any]] = []       # tabular form of the same data
    recommended_chart: str | None = None
    notes: list[str] = []
