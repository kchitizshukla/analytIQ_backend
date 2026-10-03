"""Profiling + preview services on top of cached dataframes."""
from __future__ import annotations

import math
import uuid
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.statistics import profile_dataframe
from app.models import Dataset
from app.services import data_access


def _clean(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if math.isnan(float(v)) else float(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    return v


def build_profile(dataset: Dataset) -> dict:
    loaded = data_access.load_dataset(str(dataset.id), dataset.storage_path)
    prof = profile_dataframe(loaded.df, loaded.types)
    prof["dataset_id"] = dataset.id
    return prof


def build_preview(dataset: Dataset, page: int = 1, page_size: int = 50) -> dict:
    loaded = data_access.load_dataset(str(dataset.id), dataset.storage_path)
    df = loaded.raw
    total = len(df)
    start = (page - 1) * page_size
    chunk = df.iloc[start:start + page_size]
    rows = []
    for _, r in chunk.iterrows():
        rows.append({str(k): _clean(v) for k, v in r.items()})
    return {
        "dataset_id": dataset.id,
        "columns": [str(c) for c in df.columns],
        "rows": rows,
        "total_rows": total,
        "page": page,
        "page_size": page_size,
    }
