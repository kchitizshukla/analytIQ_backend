"""Shared helpers for turning raw extracted tables into clean dataframes."""
from __future__ import annotations

import pandas as pd


def normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure every column has a clean, unique string name."""
    seen: dict[str, int] = {}
    new_cols = []
    for i, col in enumerate(df.columns):
        name = str(col).strip()
        if not name or name.lower().startswith("unnamed"):
            name = f"Column {i + 1}"
        base = name
        while name in seen:
            seen[base] = seen.get(base, 0) + 1
            name = f"{base}_{seen[base]}"
        seen[name] = 0
        new_cols.append(name)
    df = df.copy()
    df.columns = new_cols
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Drop fully-empty rows/columns and normalise headers."""
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    df = normalize_headers(df)
    # strip whitespace on object columns
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
    df = df.reset_index(drop=True)
    return df


def detect_header_row(raw: pd.DataFrame, max_scan: int = 5) -> int:
    """Heuristic: pick the first row that looks like a header (mostly text, no dup)."""
    best_row = 0
    best_score = -1.0
    for i in range(min(max_scan, len(raw))):
        row = raw.iloc[i]
        non_null = row.dropna()
        if non_null.empty:
            continue
        text_frac = non_null.map(lambda v: isinstance(v, str)).mean()
        uniq_frac = non_null.nunique() / len(non_null)
        score = text_frac * 0.6 + uniq_frac * 0.4
        if score > best_score:
            best_score = score
            best_row = i
    return best_row
