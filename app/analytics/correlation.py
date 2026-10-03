"""Correlation analysis (Pearson, deterministic)."""
from __future__ import annotations

from typing import Any

import pandas as pd


def correlation_matrix(df: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    numeric = df[columns].apply(pd.to_numeric, errors="coerce")
    corr = numeric.corr(method="pearson").round(4)
    matrix = {
        str(r): {str(c): (None if pd.isna(corr.loc[r, c]) else float(corr.loc[r, c]))
                 for c in corr.columns}
        for r in corr.index
    }

    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iloc[i, j]
            if pd.isna(v):
                continue
            pairs.append({"a": str(cols[i]), "b": str(cols[j]), "correlation": float(v)})
    pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)

    return {"matrix": matrix, "pairs": pairs}


def strongest_pair(df: pd.DataFrame, columns: list[str]) -> dict[str, Any] | None:
    result = correlation_matrix(df, columns)
    return result["pairs"][0] if result["pairs"] else None
