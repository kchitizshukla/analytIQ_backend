"""Unit tests for the deterministic analytics + type inference."""
import uuid

import pandas as pd
import pytest

from app.analytics.correlation import correlation_matrix
from app.analytics.grouping import group_aggregate
from app.analytics.outliers import count_outliers, detect_anomalies
from app.analytics.statistics import profile_dataframe
from app.analytics.trends import trend_over_time
from app.ingestion.types import infer_column_type


def test_type_inference():
    assert infer_column_type(pd.Series([1, 2, 3, 4])) == "numeric"
    assert infer_column_type(pd.Series(["$1,000", "$2,500", "$3,100"])) == "currency"
    assert infer_column_type(pd.Series(["10%", "20%", "35%"])) == "percentage"
    assert infer_column_type(pd.Series(["2026-01-01", "2026-02-01", "2026-03-01"])) == "datetime"
    assert infer_column_type(pd.Series(["yes", "no", "yes", "no"])) == "boolean"
    assert infer_column_type(pd.Series(["North", "South", "North", "East"])) == "categorical"


def test_profile(loaded):
    prof = profile_dataframe(loaded.df, loaded.types)
    assert prof["row_count"] == 24
    assert prof["column_count"] == 5
    assert "Revenue" in prof["numeric_columns"]
    assert "Date" in prof["datetime_columns"]
    assert 0 <= prof["quality_score"] <= 100


def test_group_aggregate(loaded):
    res = group_aggregate(loaded.df, "Region", ["Revenue"], {"Revenue": "sum"}, "sum", sort="desc")
    assert res["rows"]
    values = [r["Revenue"] for r in res["rows"]]
    assert values == sorted(values, reverse=True)  # sorted desc


def test_trend(loaded):
    tr = trend_over_time(loaded.df, "Date", "Revenue", "sum", "month")
    assert len(tr["categories"]) == 12
    assert tr["direction"] in ("up", "down", "flat")


def test_correlation(loaded):
    res = correlation_matrix(loaded.df, ["Revenue", "Profit"])
    assert res["pairs"]
    assert abs(res["pairs"][0]["correlation"]) > 0.9  # revenue~profit strongly correlated


def test_outliers():
    s = pd.Series([1, 2, 3, 4, 5, 1000])
    assert count_outliers(s) >= 1


def test_detect_anomalies(loaded):
    res = detect_anomalies(loaded.df, ["Revenue"])
    assert "total_anomalies" in res
    assert "per_column" in res
