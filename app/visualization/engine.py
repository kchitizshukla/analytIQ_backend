"""Visualization builder: validate config, compute data, shape chart series.

Every chart is validated against the real dataset schema before any computation.
The LLM may *suggest* a chart, but this engine is the source of truth.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.analytics.grouping import AGG_MAP, group_aggregate
from app.analytics.trends import trend_over_time
from app.ingestion.types import is_numeric_type
from app.schemas.visualization import (
    AGGREGATIONS,
    CHART_TYPES,
    FilterClause,
    SeriesData,
    VisualizationConfig,
    VisualizationResult,
)
from app.services.data_access import LoadedDataset
from app.visualization.recommend import recommend_chart


class VisualizationError(ValueError):
    """Raised when a visualization config is invalid for the dataset."""


def _apply_filters(df: pd.DataFrame, filters: list[FilterClause]) -> pd.DataFrame:
    for f in filters:
        if f.column not in df.columns:
            raise VisualizationError(f"Filter column '{f.column}' does not exist.")
        col = df[f.column]
        op, val = f.op, f.value
        if op == "eq":
            df = df[col.astype(str) == str(val)]
        elif op == "ne":
            df = df[col.astype(str) != str(val)]
        elif op == "in" and isinstance(val, list):
            df = df[col.astype(str).isin([str(v) for v in val])]
        elif op == "contains":
            df = df[col.astype(str).str.contains(str(val), case=False, na=False)]
        elif op in ("gt", "gte", "lt", "lte"):
            num = pd.to_numeric(col, errors="coerce")
            v = float(val)
            df = df[{"gt": num > v, "gte": num >= v, "lt": num < v, "lte": num <= v}[op]]
    return df


def validate_config(cfg: VisualizationConfig, loaded: LoadedDataset) -> list[str]:
    """Validate and return non-fatal notes. Raises VisualizationError on hard errors."""
    notes: list[str] = []
    types = loaded.types
    cols = set(types.keys())

    if cfg.chart_type not in CHART_TYPES:
        raise VisualizationError(f"Unsupported chart type '{cfg.chart_type}'.")

    if cfg.dimension and cfg.dimension not in cols:
        raise VisualizationError(f"Dimension '{cfg.dimension}' does not exist in this dataset.")
    if cfg.group_by and cfg.group_by not in cols:
        raise VisualizationError(f"Group-by column '{cfg.group_by}' does not exist.")

    for m in cfg.measures:
        if m not in cols:
            raise VisualizationError(f"Measure '{m}' does not exist in this dataset.")
        if not is_numeric_type(types[m]):
            raise VisualizationError(f"Measure '{m}' is not numeric and cannot be aggregated.")

    for m, agg in cfg.aggregation.items():
        if agg.lower() not in AGGREGATIONS:
            raise VisualizationError(f"Invalid aggregation '{agg}' for '{m}'.")

    if cfg.chart_type == "scatter" and len(cfg.measures) < 1:
        raise VisualizationError("Scatter charts need a dimension and at least one measure.")
    if cfg.chart_type in ("line", "area") and cfg.dimension and types.get(cfg.dimension) != "datetime":
        notes.append("Line/area charts work best with a datetime dimension.")

    return notes


def build_visualization(cfg: VisualizationConfig, loaded: LoadedDataset) -> VisualizationResult:
    notes = validate_config(cfg, loaded)
    df = _apply_filters(loaded.df.copy(), cfg.filters)
    types = loaded.types

    dim_type = types.get(cfg.dimension) if cfg.dimension else None
    measure_types = [types[m] for m in cfg.measures]
    recommended = recommend_chart(dim_type, measure_types, bool(cfg.group_by))
    chart_type = cfg.chart_type
    title = cfg.title or _auto_title(cfg)

    # --- time series ---
    if chart_type in ("line", "area") and cfg.dimension and dim_type == "datetime" and cfg.measures:
        series_list, categories = [], []
        for m in cfg.measures:
            agg = cfg.aggregation.get(m, cfg.default_aggregation)
            tr = trend_over_time(df, cfg.dimension, m, agg, "month")
            categories = tr["categories"]
            series_list.append(SeriesData(name=m, data=tr["values"]))
        rows = [{cfg.dimension: c, **{s.name: s.data[i] for s in series_list}}
                for i, c in enumerate(categories)]
        return VisualizationResult(
            dataset_id=cfg.dataset_id, chart_type=chart_type, title=title,
            dimension=cfg.dimension, measures=cfg.measures, categories=categories,
            series=series_list, rows=rows, recommended_chart=recommended, notes=notes,
        )

    # --- scatter (numeric x numeric) ---
    if chart_type == "scatter" and cfg.dimension and cfg.measures:
        x = pd.to_numeric(df[cfg.dimension], errors="coerce")
        pts_rows = []
        series_list = []
        for m in cfg.measures:
            y = pd.to_numeric(df[m], errors="coerce")
            pairs = pd.DataFrame({"x": x, "y": y}).dropna()
            if cfg.limit:
                pairs = pairs.head(cfg.limit)
            series_list.append(SeriesData(name=m, data=[[float(a), float(b)] for a, b in zip(pairs["x"], pairs["y"])]))
            pts_rows = [{cfg.dimension: float(a), m: float(b)} for a, b in zip(pairs["x"], pairs["y"])]
        return VisualizationResult(
            dataset_id=cfg.dataset_id, chart_type=chart_type, title=title,
            dimension=cfg.dimension, measures=cfg.measures, series=series_list,
            rows=pts_rows, recommended_chart=recommended, notes=notes,
        )

    # --- histogram (single numeric, no dimension) ---
    if chart_type == "histogram" and cfg.measures:
        m = cfg.measures[0]
        vals = pd.to_numeric(df[m], errors="coerce").dropna()
        counts, edges = np.histogram(vals, bins=min(20, max(5, int(np.sqrt(len(vals) or 1)))))
        categories = [f"{round(edges[i],1)}–{round(edges[i+1],1)}" for i in range(len(counts))]
        rows = [{"bin": c, "count": int(n)} for c, n in zip(categories, counts)]
        return VisualizationResult(
            dataset_id=cfg.dataset_id, chart_type=chart_type, title=title,
            measures=cfg.measures, categories=categories,
            series=[SeriesData(name=m, data=[int(n) for n in counts])],
            rows=rows, recommended_chart=recommended, notes=notes,
        )

    # --- bar / grouped_bar / pie (categorical dimension) ---
    if not cfg.dimension:
        raise VisualizationError("This chart requires a dimension.")
    if not cfg.measures:
        # count by dimension
        vc = df[cfg.dimension].astype(str).value_counts()
        if cfg.limit:
            vc = vc.head(cfg.limit)
        categories = [str(k) for k in vc.index]
        series_list = [SeriesData(name="count", data=[int(v) for v in vc.values])]
        rows = [{cfg.dimension: c, "count": int(v)} for c, v in zip(categories, vc.values)]
        return VisualizationResult(
            dataset_id=cfg.dataset_id, chart_type=chart_type, title=title,
            dimension=cfg.dimension, measures=["count"], categories=categories,
            series=series_list, rows=rows, recommended_chart=recommended, notes=notes,
        )

    agg = group_aggregate(
        df, cfg.dimension, cfg.measures, cfg.aggregation, cfg.default_aggregation,
        group_by=cfg.group_by, sort=cfg.sort or "desc", limit=cfg.limit,
    )
    rows = agg["rows"]
    categories = [r.get(cfg.dimension) for r in rows]

    if cfg.group_by:
        # pivot into one series per group value
        pivot: dict[Any, dict[Any, Any]] = {}
        groups: list[Any] = []
        measure = cfg.measures[0]
        for r in rows:
            d, g = r.get(cfg.dimension), r.get(cfg.group_by)
            pivot.setdefault(d, {})[g] = r.get(measure)
            if g not in groups:
                groups.append(g)
        categories = list(pivot.keys())
        series_list = [
            SeriesData(name=str(g), data=[pivot[d].get(g, 0) for d in categories])
            for g in groups
        ]
    else:
        series_list = [
            SeriesData(name=m, data=[r.get(m, 0) for r in rows]) for m in cfg.measures
        ]

    return VisualizationResult(
        dataset_id=cfg.dataset_id, chart_type=chart_type, title=title,
        dimension=cfg.dimension, measures=cfg.measures,
        categories=[str(c) for c in categories], series=series_list, rows=rows,
        recommended_chart=recommended, notes=notes,
    )


def _auto_title(cfg: VisualizationConfig) -> str:
    if cfg.measures and cfg.dimension:
        return f"{', '.join(cfg.measures)} by {cfg.dimension}"
    if cfg.dimension:
        return f"Count by {cfg.dimension}"
    if cfg.measures:
        return f"Distribution of {cfg.measures[0]}"
    return "Visualization"
