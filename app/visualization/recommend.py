"""Deterministic chart-type recommendation based on column semantics."""
from __future__ import annotations

from app.ingestion.types import is_numeric_type


def recommend_chart(
    dimension_type: str | None,
    measure_types: list[str],
    has_group_by: bool,
) -> str:
    n_measures = len(measure_types)

    # No dimension, single numeric measure -> histogram
    if dimension_type is None and n_measures == 1:
        return "histogram"

    # datetime x-axis -> time series
    if dimension_type == "datetime":
        if n_measures > 1 or has_group_by:
            return "line"
        return "area" if n_measures == 1 else "line"

    # two numeric columns, no categorical dimension -> scatter
    if dimension_type and is_numeric_type(dimension_type) and n_measures >= 1:
        return "scatter"

    # categorical dimension
    if dimension_type in ("categorical", "boolean", "text"):
        if n_measures == 0:
            return "pie"
        if n_measures > 1 or has_group_by:
            return "grouped_bar"
        return "bar"

    return "bar"
