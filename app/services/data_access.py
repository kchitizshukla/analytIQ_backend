"""Loads a dataset's primary dataframe from its stored file, with caching.

Keeps raw dataset content out of the database — large tables live on disk and
are loaded on demand. An LRU-ish in-process cache avoids re-parsing on every
request. This is an extension point for Redis / columnar caching later.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass

import pandas as pd

from app.ingestion.loader import load_file, primary_sheet
from app.ingestion.types import coerce_column, profile_dataframe_types

_CACHE_MAX = 16
_cache: "OrderedDict[str, LoadedDataset]" = OrderedDict()
_lock = threading.Lock()


@dataclass
class LoadedDataset:
    df: pd.DataFrame          # typed/coerced dataframe for analytics
    raw: pd.DataFrame         # cleaned but original-typed dataframe (for preview)
    types: dict[str, str]
    sheet_name: str


def _build(path: str) -> LoadedDataset:
    result = load_file(path)
    sheet_name, raw = primary_sheet(result["sheets"])
    types = profile_dataframe_types(raw)
    typed = raw.copy()
    for col in typed.columns:
        typed[col] = coerce_column(typed[col], types[str(col)])
    return LoadedDataset(df=typed, raw=raw, types=types, sheet_name=sheet_name)


def load_dataset(dataset_id: str, path: str) -> LoadedDataset:
    key = f"{dataset_id}:{path}"
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    loaded = _build(path)
    with _lock:
        _cache[key] = loaded
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return loaded


def invalidate(dataset_id: str) -> None:
    with _lock:
        for k in [k for k in _cache if k.startswith(f"{dataset_id}:")]:
            _cache.pop(k, None)
