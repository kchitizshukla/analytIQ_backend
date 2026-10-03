"""Outlier / anomaly detection (deterministic)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def iqr_bounds(series: pd.Series) -> tuple[float, float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return (float("nan"), float("nan"))
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return (q1 - 1.5 * iqr, q3 + 1.5 * iqr)


def count_outliers(series: pd.Series) -> int:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return 0
    lo, hi = iqr_bounds(s)
    return int(((s < lo) | (s > hi)).sum())


def detect_anomalies(
    df: pd.DataFrame, columns: list[str], limit: int = 20
) -> dict[str, Any]:
    """Flag rows that are outliers on one or more numeric columns (IQR method)."""
    flags = pd.Series(False, index=df.index)
    per_column: dict[str, dict[str, Any]] = {}
    for col in columns:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        lo, hi = iqr_bounds(s)
        if np.isnan(lo):
            continue
        mask = (s < lo) | (s > hi)
        flags = flags | mask.fillna(False)
        per_column[col] = {
            "lower_bound": round(float(lo), 2),
            "upper_bound": round(float(hi), 2),
            "outlier_count": int(mask.fillna(False).sum()),
        }

    anomalous = df[flags].head(limit)
    rows = _records(anomalous)
    return {
        "total_anomalies": int(flags.sum()),
        "per_column": per_column,
        "rows": rows,
    }


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for _, row in df.iterrows():
        rec = {}
        for k, v in row.items():
            if pd.isna(v):
                rec[str(k)] = None
            elif isinstance(v, (np.integer,)):
                rec[str(k)] = int(v)
            elif isinstance(v, (np.floating, float)):
                rec[str(k)] = round(float(v), 4)
            else:
                rec[str(k)] = str(v)
        out.append(rec)
    return out
