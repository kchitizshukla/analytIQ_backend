"""Time-series trend analysis (deterministic)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FREQ_MAP = {"day": "D", "week": "W", "month": "MS", "quarter": "QS", "year": "YS"}


def trend_over_time(
    df: pd.DataFrame,
    date_column: str,
    measure: str,
    aggregation: str = "sum",
    frequency: str = "month",
) -> dict[str, Any]:
    work = df[[date_column, measure]].copy()
    work[date_column] = pd.to_datetime(work[date_column], errors="coerce")
    work[measure] = pd.to_numeric(work[measure], errors="coerce")
    work = work.dropna(subset=[date_column])

    freq = FREQ_MAP.get(frequency, "MS")
    agg = {"sum": "sum", "mean": "mean", "avg": "mean", "count": "count",
           "min": "min", "max": "max", "median": "median"}.get(aggregation, "sum")

    resampled = work.set_index(date_column).resample(freq)[measure].agg(agg).fillna(0)

    categories = [d.strftime("%Y-%m-%d") for d in resampled.index]
    values = [round(float(v), 4) for v in resampled.values]

    change = None
    pct_change = None
    if len(values) >= 2 and values[0] != 0:
        change = round(values[-1] - values[0], 4)
        pct_change = round((values[-1] - values[0]) / abs(values[0]) * 100, 2)

    # simple linear slope
    slope = None
    if len(values) >= 2:
        x = np.arange(len(values))
        slope = float(np.polyfit(x, values, 1)[0])

    peak_idx = int(np.argmax(values)) if values else None
    trough_idx = int(np.argmin(values)) if values else None

    return {
        "categories": categories,
        "values": values,
        "frequency": frequency,
        "first": values[0] if values else None,
        "last": values[-1] if values else None,
        "change": change,
        "pct_change": pct_change,
        "slope": slope,
        "direction": ("up" if slope and slope > 0 else "down" if slope and slope < 0 else "flat"),
        "peak": {"period": categories[peak_idx], "value": values[peak_idx]} if peak_idx is not None else None,
        "trough": {"period": categories[trough_idx], "value": values[trough_idx]} if trough_idx is not None else None,
    }
