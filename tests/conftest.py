import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.data_access import LoadedDataset  # noqa: E402
from app.ingestion.types import coerce_column, profile_dataframe_types  # noqa: E402


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=12, freq="MS").astype(str).tolist() * 2,
        "Region": (["North", "South", "East", "West"] * 6),
        "Product": (["A", "B", "C"] * 8),
        "Revenue": [100, 200, 150, 300, 250, 400, 120, 220, 180, 320, 260, 410] * 2,
        "Profit": [30, 60, 45, 90, 75, 120, 36, 66, 54, 96, 78, 123] * 2,
    })


@pytest.fixture
def loaded(sample_df) -> LoadedDataset:
    types = profile_dataframe_types(sample_df)
    typed = sample_df.copy()
    for c in typed.columns:
        typed[c] = coerce_column(typed[c], types[str(c)])
    return LoadedDataset(df=typed, raw=sample_df, types=types, sheet_name="Sheet1")
