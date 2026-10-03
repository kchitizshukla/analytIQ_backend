"""Tests for the AI query engine's validation + execution (safety boundary)."""
import uuid

import pytest

from app.ai.query_engine import PlanError, execute_plan
from app.visualization.engine import VisualizationError, build_visualization
from app.schemas.visualization import VisualizationConfig

DID = uuid.uuid4()


def test_groupby_plan(loaded):
    out = execute_plan(
        {"operation": "groupby", "dimension": "Region", "measure": "Revenue",
         "aggregation": "sum", "sort": "desc"}, loaded, DID)
    assert out.response_type == "visualization"
    assert out.visualization is not None


def test_invalid_column_rejected(loaded):
    with pytest.raises(PlanError):
        execute_plan({"operation": "groupby", "dimension": "Ghost", "measure": "Revenue"},
                     loaded, DID)


def test_non_numeric_measure_rejected(loaded):
    with pytest.raises(PlanError):
        execute_plan({"operation": "aggregate", "measure": "Region", "aggregation": "sum"},
                     loaded, DID)


def test_unsupported_operation_rejected(loaded):
    with pytest.raises(PlanError):
        execute_plan({"operation": "drop_table"}, loaded, DID)


def test_trend_plan(loaded):
    out = execute_plan(
        {"operation": "trend", "date_column": "Date", "measure": "Revenue",
         "aggregation": "sum", "frequency": "month"}, loaded, DID)
    assert out.visualization.chart_type == "line"


def test_aggregate_kpi(loaded):
    out = execute_plan({"operation": "aggregate", "measure": "Revenue", "aggregation": "mean"},
                       loaded, DID)
    assert out.response_type == "kpi"
    assert out.kpis


def test_visualization_validation_rejects_bad_chart(loaded):
    cfg = VisualizationConfig(dataset_id=DID, chart_type="bogus", dimension="Region",
                              measures=["Revenue"])
    with pytest.raises(VisualizationError):
        build_visualization(cfg, loaded)


def test_visualization_recommendation(loaded):
    cfg = VisualizationConfig(dataset_id=DID, chart_type="bar", dimension="Region",
                              measures=["Revenue"], aggregation={"Revenue": "sum"})
    result = build_visualization(cfg, loaded)
    assert result.recommended_chart == "bar"
    assert result.categories
    assert result.series
