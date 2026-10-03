"""Group-by aggregation + ranking (deterministic)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

AGG_MAP = {
    "sum": "sum",
    "mean": "mean",
    "avg": "mean",
    "count": "count",
    "min": "min",
    "max": "max",
    "median": "median",
}


def _clean_val(v: Any) -> Any:
    if pd.isna(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return round(float(v), 4)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    return str(v)


def group_aggregate(
    df: pd.DataFrame,
    dimension: str,
    measures: list[str],
    aggregation: dict[str, str] | None = None,
    default_agg: str = "sum",
    group_by: str | None = None,
    sort: str | None = "desc",
    limit: int | None = None,
) -> dict[str, Any]:
    """Group df by dimension (and optional secondary group_by) and aggregate measures."""
    aggregation = aggregation or {}
    group_cols = [c for c in [dimension, group_by] if c]
    if not group_cols:
        raise ValueError("A dimension is required for grouping.")

    work = df.copy()
    for m in measures:
        work[m] = pd.to_numeric(work[m], errors="coerce")

    agg_spec = {m: AGG_MAP.get(aggregation.get(m, default_agg), "sum") for m in measures}
    grouped = work.groupby(group_cols, dropna=False).agg(agg_spec).reset_index()

    # sort by first measure
    if measures and sort in ("asc", "desc"):
        grouped = grouped.sort_values(measures[0], ascending=(sort == "asc"))
    if limit:
        grouped = grouped.head(limit)

    records = [{str(k): _clean_val(v) for k, v in row.items()} for _, row in grouped.iterrows()]
    return {
        "group_cols": group_cols,
        "measures": measures,
        "rows": records,
    }


def descriptive_group(df: pd.DataFrame, dimension: str, measure: str) -> dict[str, Any]:
    work = df.copy()
    work[measure] = pd.to_numeric(work[measure], errors="coerce")
    g = work.groupby(dimension, dropna=False)[measure].agg(["sum", "mean", "count"]).reset_index()
    g = g.sort_values("sum", ascending=False)
    return {
        "rows": [{str(k): _clean_val(v) for k, v in row.items()} for _, row in g.iterrows()]
    }
