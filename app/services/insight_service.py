"""Generates numerically-grounded insights.

All numbers come from deterministic analytics. The LLM only rephrases them into
polished prose; when it is unavailable we fall back to templated descriptions.
Every insight is backed by data in the `data` payload.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.ai import prompts
from app.ai.analyst import _extract_json
from app.ai.provider import LLMUnavailable, get_provider
from app.analytics.correlation import correlation_matrix
from app.analytics.grouping import group_aggregate
from app.analytics.outliers import detect_anomalies
from app.analytics.statistics import profile_dataframe
from app.analytics.trends import trend_over_time
from app.core.logging import get_logger
from app.ingestion.types import is_numeric_type
from app.models import Dataset
from app.repositories import dataset_repo
from app.services import data_access

logger = get_logger("insight_service")


def _compute_analytics(loaded) -> dict:
    df, types = loaded.df, loaded.types
    numeric = [c for c, t in types.items() if is_numeric_type(t)]
    categorical = [c for c, t in types.items() if t in ("categorical", "boolean", "text")]
    datetimes = [c for c, t in types.items() if t == "datetime"]
    out: dict = {"facts": []}

    prof = profile_dataframe(df, types)
    out["profile"] = {k: prof[k] for k in ("row_count", "column_count", "completeness",
                                           "duplicate_rows", "missing_percentage", "quality_score")}

    if datetimes and numeric:
        tr = trend_over_time(df, datetimes[0], numeric[0], "sum", "month")
        out["trend"] = {"measure": numeric[0], "date": datetimes[0], **{
            k: tr[k] for k in ("pct_change", "direction", "first", "last", "peak", "trough")}}

    if categorical and numeric:
        g = group_aggregate(df, categorical[0], [numeric[0]], {numeric[0]: "sum"}, "sum", sort="desc", limit=3)
        out["top_category"] = {"dimension": categorical[0], "measure": numeric[0], "rows": g["rows"]}

    if len(numeric) >= 2:
        corr = correlation_matrix(df, numeric[:6])
        out["correlation"] = {"top_pairs": corr["pairs"][:3]}

    if numeric:
        an = detect_anomalies(df, numeric[:3], limit=5)
        out["anomaly"] = {"total": an["total_anomalies"], "per_column": an["per_column"]}

    return out


def _template_insights(analytics: dict) -> list[dict]:
    insights: list[dict] = []
    prof = analytics.get("profile", {})
    insights.append({
        "insight_type": "summary",
        "title": "Dataset overview",
        "description": (f"{prof.get('row_count', 0):,} rows across "
                        f"{prof.get('column_count', 0)} columns with "
                        f"{prof.get('completeness', 0)}% completeness and "
                        f"{prof.get('duplicate_rows', 0)} duplicate rows."),
        "severity": "info",
        "data": prof,
    })
    tr = analytics.get("trend")
    if tr and tr.get("pct_change") is not None:
        sev = "positive" if (tr["pct_change"] or 0) >= 0 else "warning"
        insights.append({
            "insight_type": "trend",
            "title": f"{tr['measure']} is trending {tr['direction']}",
            "description": (f"{tr['measure']} changed {tr['pct_change']}% over the period, "
                            f"from {tr['first']} to {tr['last']}. Peak: "
                            f"{(tr.get('peak') or {}).get('period')}."),
            "severity": sev,
            "data": tr,
        })
    tc = analytics.get("top_category")
    if tc and tc["rows"]:
        top = tc["rows"][0]
        insights.append({
            "insight_type": "comparison",
            "title": f"Top {tc['dimension']} by {tc['measure']}",
            "description": (f"{top.get(tc['dimension'])} leads with "
                            f"{top.get(tc['measure'])} in total {tc['measure']}."),
            "severity": "info",
            "data": tc,
        })
    corr = analytics.get("correlation")
    if corr and corr["top_pairs"]:
        p = corr["top_pairs"][0]
        insights.append({
            "insight_type": "correlation",
            "title": f"{p['a']} and {p['b']} move together",
            "description": (f"{p['a']} and {p['b']} have a correlation of {p['correlation']}, "
                            "indicating a strong relationship."),
            "severity": "info",
            "data": corr,
        })
    an = analytics.get("anomaly")
    if an and an.get("total", 0) > 0:
        insights.append({
            "insight_type": "anomaly",
            "title": f"{an['total']} anomalies detected",
            "description": (f"{an['total']} records fall outside the expected range on "
                            "one or more numeric columns and may warrant review."),
            "severity": "warning",
            "data": an,
        })
    return insights


def generate_insights(db: Session, dataset: Dataset) -> tuple[list[dict], bool]:
    loaded = data_access.load_dataset(str(dataset.id), dataset.storage_path)
    analytics = _compute_analytics(loaded)
    templated = _template_insights(analytics)

    used_ai = False
    provider = get_provider()
    if provider.available:
        try:
            raw = provider.generate(
                prompts.INSIGHTS_SYSTEM,
                prompts.insights_prompt(dataset.name, analytics),
                json_mode=True, temperature=0.4,
            )
            parsed = _extract_json(raw)
            ai_items = parsed.get("insights", [])
            if ai_items:
                # attach deterministic data payloads by type where available
                data_by_type = {i["insight_type"]: i["data"] for i in templated}
                merged = []
                for item in ai_items:
                    item.setdefault("severity", "info")
                    item["data"] = data_by_type.get(item.get("insight_type"), {})
                    merged.append(item)
                templated = merged
                used_ai = True
        except (LLMUnavailable, ValueError) as exc:
            logger.warning("AI insight phrasing failed (%s); using templates.", exc)

    saved = dataset_repo.replace_insights(db, dataset.id, templated)
    db.commit()
    return (
        [{"id": s.id, "insight_type": s.insight_type, "title": s.title,
          "description": s.description, "data": s.data, "severity": s.severity,
          "created_at": s.created_at} for s in saved],
        used_ai,
    )
