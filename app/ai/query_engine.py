"""Validates and executes structured analytical plans.

This is the hard safety boundary between the LLM and the data. The LLM proposes a
plan (JSON); this module validates every field against the real dataset schema and
then runs ONLY deterministic Pandas analytics. Invalid plans are rejected or
repaired — never executed as-is, never turned into SQL or Python.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.analytics.correlation import correlation_matrix
from app.analytics.grouping import AGG_MAP, descriptive_group, group_aggregate
from app.analytics.outliers import detect_anomalies
from app.analytics.statistics import describe_numeric
from app.analytics.trends import trend_over_time
from app.ingestion.types import is_numeric_type
from app.schemas.assistant import KpiCard
from app.schemas.visualization import SeriesData, VisualizationResult
from app.services.data_access import LoadedDataset

SUPPORTED_OPS = {
    "groupby", "trend", "correlation", "anomaly", "compare",
    "aggregate", "chart", "summary", "clarify",
}


class PlanError(ValueError):
    pass


class ExecutionOutcome:
    def __init__(self, response_type: str, data: dict[str, Any],
                 kpis: list[KpiCard] | None = None,
                 visualization: VisualizationResult | None = None,
                 result_summary: str = ""):
        self.response_type = response_type
        self.data = data
        self.kpis = kpis or []
        self.visualization = visualization
        self.result_summary = result_summary


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def _require_col(col: str | None, loaded: LoadedDataset, *, numeric=False, datetime=False) -> str:
    if not col or col not in loaded.types:
        raise PlanError(f"Column '{col}' does not exist in this dataset.")
    t = loaded.types[col]
    if numeric and not is_numeric_type(t):
        raise PlanError(f"Column '{col}' is not numeric.")
    if datetime and t != "datetime":
        raise PlanError(f"Column '{col}' is not a date/time column.")
    return col


def _valid_agg(agg: str | None) -> str:
    agg = (agg or "sum").lower()
    if agg not in AGG_MAP:
        raise PlanError(f"Unsupported aggregation '{agg}'.")
    return agg


def _first_datetime(loaded: LoadedDataset) -> str | None:
    for c, t in loaded.types.items():
        if t == "datetime":
            return c
    return None


def _numeric_cols(loaded: LoadedDataset) -> list[str]:
    return [c for c, t in loaded.types.items() if is_numeric_type(t)]


# --------------------------------------------------------------------------- #
# Executor
# --------------------------------------------------------------------------- #
def execute_plan(plan: dict[str, Any], loaded: LoadedDataset, dataset_id) -> ExecutionOutcome:
    op = plan.get("operation")
    if op not in SUPPORTED_OPS:
        raise PlanError(f"Unsupported operation '{op}'.")
    df = loaded.df

    if op == "clarify":
        return ExecutionOutcome(
            "clarification",
            {"question": plan.get("question", "Could you clarify?"),
             "options": plan.get("options", [])},
            result_summary="clarification requested",
        )

    if op == "aggregate":
        measure = _require_col(plan.get("measure"), loaded, numeric=True)
        agg = _valid_agg(plan.get("aggregation"))
        series = pd.to_numeric(df[measure], errors="coerce")
        value = {
            "sum": series.sum(), "mean": series.mean(), "min": series.min(),
            "max": series.max(), "median": series.median(), "count": series.count(),
        }[agg if agg != "avg" else "mean"]
        value = round(float(value), 2)
        kpi = KpiCard(label=f"{agg.title()} of {measure}", value=_fmt(value))
        return ExecutionOutcome("kpi", {"measure": measure, "aggregation": agg, "value": value},
                                kpis=[kpi], result_summary=f"{agg} of {measure} = {value}")

    if op == "groupby":
        dim = _require_col(plan.get("dimension"), loaded)
        measure = _require_col(plan.get("measure"), loaded, numeric=True)
        agg = _valid_agg(plan.get("aggregation"))
        group_by = plan.get("group_by")
        if group_by:
            group_by = _require_col(group_by, loaded)
        sort = plan.get("sort", "desc")
        limit = plan.get("limit")
        res = group_aggregate(df, dim, [measure], {measure: agg}, agg,
                              group_by=group_by, sort=sort if sort in ("asc", "desc") else "desc",
                              limit=limit)
        rows = res["rows"]
        viz = _grouped_viz(dataset_id, "bar", dim, measure, rows, group_by)
        top = rows[0] if rows else {}
        summary = f"Top {dim} by {agg}({measure}): {top.get(dim)} = {top.get(measure)}" if rows else "no rows"
        return ExecutionOutcome("visualization", {"rows": rows}, visualization=viz, result_summary=summary)

    if op == "compare":
        dim = _require_col(plan.get("dimension"), loaded)
        measure = _require_col(plan.get("measure"), loaded, numeric=True)
        agg = _valid_agg(plan.get("aggregation"))
        values = plan.get("values") or []
        sub = df[df[dim].astype(str).isin([str(v) for v in values])] if values else df
        res = group_aggregate(sub, dim, [measure], {measure: agg}, agg, sort="desc")
        rows = res["rows"]
        viz = _grouped_viz(dataset_id, "bar", dim, measure, rows, None)
        summary = "; ".join(f"{r.get(dim)}: {r.get(measure)}" for r in rows[:5])
        return ExecutionOutcome("visualization", {"rows": rows}, visualization=viz, result_summary=summary)

    if op == "trend":
        date_col = plan.get("date_column") or _first_datetime(loaded)
        _require_col(date_col, loaded, datetime=True)
        measure = _require_col(plan.get("measure"), loaded, numeric=True)
        agg = _valid_agg(plan.get("aggregation"))
        freq = plan.get("frequency", "month")
        tr = trend_over_time(df, date_col, measure, agg, freq)
        viz = VisualizationResult(
            dataset_id=dataset_id, chart_type="line",
            title=f"{measure} over time ({freq})", dimension=date_col, measures=[measure],
            categories=tr["categories"], series=[SeriesData(name=measure, data=tr["values"])],
            rows=[{date_col: c, measure: v} for c, v in zip(tr["categories"], tr["values"])],
        )
        summary = (f"{measure} {tr['direction']} overall; change {tr.get('pct_change')}% "
                   f"from {tr.get('first')} to {tr.get('last')}")
        return ExecutionOutcome("visualization", {"trend": tr}, visualization=viz, result_summary=summary)

    if op == "correlation":
        cols = plan.get("columns") or _numeric_cols(loaded)[:6]
        cols = [_require_col(c, loaded, numeric=True) for c in cols if c in loaded.types]
        if len(cols) < 2:
            raise PlanError("Correlation needs at least two numeric columns.")
        res = correlation_matrix(df, cols)
        top = res["pairs"][0] if res["pairs"] else None
        summary = (f"Strongest correlation: {top['a']} vs {top['b']} = {top['correlation']}"
                   if top else "no correlations")
        return ExecutionOutcome("analysis", {"correlation": res}, result_summary=summary)

    if op == "anomaly":
        cols = plan.get("columns") or _numeric_cols(loaded)[:4]
        cols = [_require_col(c, loaded, numeric=True) for c in cols if c in loaded.types]
        if not cols:
            raise PlanError("Anomaly detection needs numeric columns.")
        res = detect_anomalies(df, cols)
        summary = f"{res['total_anomalies']} anomalous rows across {cols}"
        return ExecutionOutcome("analysis", {"anomaly": res}, result_summary=summary)

    if op == "chart":
        from app.schemas.visualization import VisualizationConfig
        from app.visualization.engine import build_visualization
        measures = [m for m in (plan.get("measures") or []) if m in loaded.types]
        cfg = VisualizationConfig(
            dataset_id=dataset_id,
            chart_type=plan.get("chart_type", "bar"),
            dimension=plan.get("dimension"),
            measures=measures,
            group_by=plan.get("group_by"),
            default_aggregation=_valid_agg(plan.get("aggregation")),
            aggregation={m: _valid_agg(plan.get("aggregation")) for m in measures},
        )
        viz = build_visualization(cfg, loaded)
        return ExecutionOutcome("visualization", {"rows": viz.rows}, visualization=viz,
                                result_summary=f"chart: {viz.title}")

    if op == "summary":
        from app.analytics.statistics import profile_dataframe
        prof = profile_dataframe(df, loaded.types)
        kpis = [
            KpiCard(label="Rows", value=_fmt(prof["row_count"])),
            KpiCard(label="Columns", value=_fmt(prof["column_count"])),
            KpiCard(label="Completeness", value=f"{prof['completeness']}%"),
            KpiCard(label="Duplicates", value=_fmt(prof["duplicate_rows"])),
        ]
        return ExecutionOutcome("analysis", {"profile": prof}, kpis=kpis,
                                result_summary="dataset summary")

    raise PlanError(f"Operation '{op}' is not implemented.")


def _grouped_viz(dataset_id, chart_type, dim, measure, rows, group_by) -> VisualizationResult:
    if group_by:
        pivot: dict[Any, dict[Any, Any]] = {}
        groups: list[Any] = []
        for r in rows:
            d, g = r.get(dim), r.get(group_by)
            pivot.setdefault(d, {})[g] = r.get(measure)
            if g not in groups:
                groups.append(g)
        categories = list(pivot.keys())
        series = [SeriesData(name=str(g), data=[pivot[d].get(g, 0) for d in categories]) for g in groups]
        return VisualizationResult(dataset_id=dataset_id, chart_type="grouped_bar",
                                   title=f"{measure} by {dim} / {group_by}",
                                   dimension=dim, measures=[measure],
                                   categories=[str(c) for c in categories], series=series, rows=rows)
    categories = [str(r.get(dim)) for r in rows]
    series = [SeriesData(name=measure, data=[r.get(measure, 0) for r in rows])]
    return VisualizationResult(dataset_id=dataset_id, chart_type=chart_type,
                               title=f"{measure} by {dim}", dimension=dim, measures=[measure],
                               categories=categories, series=series, rows=rows)


def _fmt(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1_000_000:
        return f"{f/1_000_000:.2f}M"
    if abs(f) >= 1_000:
        return f"{f/1_000:.1f}K"
    if f == int(f):
        return f"{int(f):,}"
    return f"{f:,.2f}"
