"""Dynamic column type inference.

Column names are never assumed — types are inferred from the data itself. The
inferred types drive the whole frontend (column selectors, chart recommendation,
assistant planning), so this is deliberately conservative and deterministic.

Inferred types: numeric | currency | percentage | datetime | boolean |
categorical | text
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

CURRENCY_RE = re.compile(r"^\s*[-+]?[$€£₹¥]\s?[\d,]+(\.\d+)?\s*$")
PERCENT_RE = re.compile(r"^\s*[-+]?[\d,]+(\.\d+)?\s?%\s*$")
NUMERIC_CLEAN_RE = re.compile(r"[,$€£₹¥%\s]")
BOOL_TRUE = {"true", "yes", "y", "1", "t"}
BOOL_FALSE = {"false", "no", "n", "0", "f"}


def _clean_numeric_series(s: pd.Series) -> pd.Series:
    cleaned = s.astype(str).str.replace(NUMERIC_CLEAN_RE, "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def _frac_match(sample: pd.Series, pattern: re.Pattern) -> float:
    if sample.empty:
        return 0.0
    matches = sample.astype(str).str.match(pattern)
    return float(matches.mean())


def infer_column_type(series: pd.Series) -> str:
    """Return the inferred semantic type for a single column."""
    non_null = series.dropna()
    if non_null.empty:
        return "text"

    # Already-typed frames (e.g. from Excel/parquet)
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        nunique = non_null.nunique()
        # small set of integers -> treat as categorical code only if truly few
        return "numeric"

    sample = non_null.astype(str).str.strip()
    sample = sample[sample != ""]
    if sample.empty:
        return "text"
    probe = sample.sample(min(len(sample), 500), random_state=0)

    # currency / percentage (string-formatted)
    if _frac_match(probe, CURRENCY_RE) >= 0.8:
        return "currency"
    if _frac_match(probe, PERCENT_RE) >= 0.8:
        return "percentage"

    # boolean
    lowered = probe.str.lower()
    if lowered.isin(BOOL_TRUE | BOOL_FALSE).mean() >= 0.95 and lowered.nunique() <= 2:
        return "boolean"

    # numeric (plain numbers stored as text)
    numeric = _clean_numeric_series(probe)
    if numeric.notna().mean() >= 0.9:
        return "numeric"

    # datetime
    parsed = pd.to_datetime(probe, errors="coerce", format="mixed", dayfirst=False)
    if parsed.notna().mean() >= 0.85:
        return "datetime"

    # categorical vs free text
    nunique = sample.nunique()
    ratio = nunique / len(sample)
    if nunique <= 50 or ratio <= 0.5:
        return "categorical"
    return "text"


def coerce_column(series: pd.Series, inferred: str) -> pd.Series:
    """Return a typed version of the column suited to analytics."""
    if inferred in ("numeric", "currency", "percentage"):
        if pd.api.types.is_numeric_dtype(series):
            return series
        return _clean_numeric_series(series)
    if inferred == "datetime":
        if pd.api.types.is_datetime64_any_dtype(series):
            return series
        return pd.to_datetime(series, errors="coerce", format="mixed")
    if inferred == "boolean":
        if pd.api.types.is_bool_dtype(series):
            return series
        lowered = series.astype(str).str.strip().str.lower()
        return lowered.map(lambda v: True if v in BOOL_TRUE else (False if v in BOOL_FALSE else np.nan))
    return series.astype("string")


def is_numeric_type(t: str) -> bool:
    return t in ("numeric", "currency", "percentage")


def is_categorical_type(t: str) -> bool:
    return t in ("categorical", "boolean", "text")


def profile_dataframe_types(df: pd.DataFrame) -> dict[str, str]:
    """Infer types for every column in a dataframe."""
    return {str(col): infer_column_type(df[col]) for col in df.columns}
