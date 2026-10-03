"""Descriptive statistics and dataset profiling. Deterministic."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.outliers import count_outliers
from app.ingestion.types import is_numeric_type


def _safe(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, (np.floating, float)):
        return None if (math.isnan(x) or math.isinf(x)) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def describe_numeric(series: pd.Series) -> dict[str, Any]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return {}
    return {
        "min": _safe(s.min()),
        "max": _safe(s.max()),
        "mean": _safe(s.mean()),
        "median": _safe(s.median()),
        "std": _safe(s.std()),
        "sum": _safe(s.sum()),
        "p25": _safe(s.quantile(0.25)),
        "p75": _safe(s.quantile(0.75)),
        "p90": _safe(s.quantile(0.90)),
    }


def describe_categorical(series: pd.Series, top_n: int = 5) -> dict[str, Any]:
    vc = series.dropna().astype(str).value_counts().head(top_n)
    return {
        "top_values": [{"value": k, "count": int(v)} for k, v in vc.items()],
    }


def profile_dataframe(df: pd.DataFrame, types: dict[str, str]) -> dict[str, Any]:
    """Full data profile: quality, per-column stats, column buckets."""
    row_count = int(len(df))
    col_count = int(len(df.columns))
    total_cells = row_count * col_count or 1

    missing_total = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())

    numeric_cols, categorical_cols, datetime_cols = [], [], []
    columns: list[dict[str, Any]] = []

    for col in df.columns:
        t = types.get(str(col), "text")
        series = df[col]
        null_count = int(series.isna().sum())
        null_pct = round(100 * null_count / row_count, 2) if row_count else 0.0
        unique_count = int(series.dropna().nunique())
        entry: dict[str, Any] = {
            "name": str(col),
            "type": t,
            "null_count": null_count,
            "null_percentage": null_pct,
            "unique_count": unique_count,
        }
        if is_numeric_type(t):
            numeric_cols.append(str(col))
            num = pd.to_numeric(series, errors="coerce")
            desc = describe_numeric(num)
            entry.update(desc)
            entry["outlier_count"] = count_outliers(num)
        elif t == "datetime":
            datetime_cols.append(str(col))
        else:
            categorical_cols.append(str(col))
            entry.update(describe_categorical(series))
        columns.append(entry)

    completeness = round(100 * (1 - missing_total / total_cells), 2)
    dup_penalty = (duplicate_rows / row_count * 100) if row_count else 0
    quality_score = round(max(0.0, min(100.0, completeness - dup_penalty * 0.5)), 1)

    return {
        "row_count": row_count,
        "column_count": col_count,
        "missing_values": missing_total,
        "missing_percentage": round(100 * missing_total / total_cells, 2),
        "duplicate_rows": duplicate_rows,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "datetime_columns": datetime_cols,
        "completeness": completeness,
        "quality_score": quality_score,
        "columns": columns,
    }
