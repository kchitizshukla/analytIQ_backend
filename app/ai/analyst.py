"""AnalytIQ Assistant orchestration.

Pipeline:  question -> plan (LLM or heuristic) -> validate+execute (deterministic)
           -> explain (LLM or template) -> follow-ups.

The heuristic planner keeps the entire assistant functional when the LLM is
unavailable, so the product never hard-depends on an external API.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.ai import prompts
from app.ai.provider import LLMUnavailable, get_provider
from app.core.logging import get_logger
from app.ingestion.types import is_numeric_type
from app.services.data_access import LoadedDataset

logger = get_logger("ai.analyst")

# NOTE: "highest"/"lowest" describe ranking direction (sort), not the aggregation,
# so they are handled by sort order — not mapped to max/min here.
_AGG_WORDS = {
    "average": "mean", "avg": "mean", "mean": "mean", "total": "sum", "sum": "sum",
    "count": "count", "number of": "count", "maximum": "max",
    "minimum": "min", "median": "median",
}


# Words stripped when deriving a concise conversation title from the first query.
_TITLE_STOP = {
    "what", "whats", "which", "who", "whom", "show", "me", "can", "you", "please",
    "tell", "give", "is", "are", "was", "were", "the", "a", "an", "of", "do", "does",
    "did", "i", "we", "how", "could", "would", "will", "to", "my", "our", "us",
    "about", "there", "here", "any", "that", "this", "it", "and", "with", "on",
    "get", "find", "list", "display", "please", "data", "dataset",
}


def generate_title(question: str, max_words: int = 6) -> str:
    """Derive a short, meaningful conversation title (~3-6 words) from a query.

    Deterministic by design so creating a conversation never costs an extra LLM
    round-trip. Not the full question — filler/question words are dropped.
    """
    q = (question or "").strip()
    if not q:
        return "New conversation"
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'+%/.-]*", q)
    content = [t for t in tokens if t.lower() not in _TITLE_STOP]
    chosen = (content or tokens)[:max_words]
    title = " ".join(chosen).strip()
    if not title:
        title = q[:48]
    # Sentence case: capitalise the first character, preserve the rest
    # (keeps acronyms / proper-ish tokens like "Q3", "North").
    title = title[0].upper() + title[1:]
    return title[:80]


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def plan_question(question: str, loaded: LoadedDataset, recent: list[dict]) -> tuple[dict, bool]:
    """Return (plan, used_llm)."""
    provider = get_provider()
    if provider.available:
        try:
            raw = provider.generate(
                prompts.PLANNER_SYSTEM,
                prompts.planner_prompt(question, loaded.types, recent),
                json_mode=True,
            )
            parsed = _extract_json(raw)
            plan = parsed.get("plan", parsed)
            if isinstance(plan, dict) and plan.get("operation"):
                return plan, True
        except (LLMUnavailable, json.JSONDecodeError, ValueError) as exc:
            logger.warning("LLM planning failed (%s); using heuristic planner.", exc)
    return heuristic_plan(question, loaded, recent), False


def heuristic_plan(question: str, loaded: LoadedDataset, recent: list[dict]) -> dict:
    """Deterministic keyword-based planner (LLM-free fallback)."""
    q = question.lower()
    types = loaded.types
    numeric = [c for c, t in types.items() if is_numeric_type(t)]
    categorical = [c for c, t in types.items() if t in ("categorical", "boolean", "text")]
    datetimes = [c for c, t in types.items() if t == "datetime"]

    def match_col(cands: list[str]) -> str | None:
        for c in cands:
            if c.lower() in q:
                return c
        return None

    # carry context: if the user says "what about profit" reuse last dimension/date
    last_plan = _last_plan(recent)

    agg = "sum"
    for word, a in _AGG_WORDS.items():
        if word in q:
            agg = a
            break

    # summary
    if any(w in q for w in ["summarize", "summary", "overview", "describe the dataset", "tell me about"]):
        return {"operation": "summary"}

    # anomaly
    if any(w in q for w in ["anomal", "unusual", "outlier", "strange", "suspicious"]):
        cols = [match_col(numeric)] if match_col(numeric) else numeric[:3]
        return {"operation": "anomaly", "columns": [c for c in cols if c]}

    # correlation / relationship
    if any(w in q for w in ["correlat", "relationship", "related", "relate"]):
        found = [c for c in numeric if c.lower() in q]
        return {"operation": "correlation", "columns": found or numeric[:4]}

    # trend / over time / monthly
    if any(w in q for w in ["trend", "over time", "monthly", "month", "daily", "weekly", "quarter", "yearly", "timeline", "decline", "grow"]):
        date_col = match_col(datetimes) or (datetimes[0] if datetimes else None)
        measure = match_col(numeric) or (last_plan.get("measure") if last_plan else None) or (numeric[0] if numeric else None)
        if date_col and measure:
            freq = "month"
            if "daily" in q or "day" in q: freq = "day"
            elif "week" in q: freq = "week"
            elif "quarter" in q: freq = "quarter"
            elif "year" in q: freq = "year"
            return {"operation": "trend", "date_column": date_col, "measure": measure,
                    "aggregation": "sum" if agg == "sum" else agg, "frequency": freq}

    # average / single aggregate ("what is the average revenue")
    if agg != "sum" and match_col(numeric) and not match_col(categorical):
        return {"operation": "aggregate", "measure": match_col(numeric), "aggregation": agg}
    if any(w in q for w in ["average order value", "average revenue", "total revenue", "average", "what is the"]) and match_col(numeric) and not match_col(categorical):
        return {"operation": "aggregate", "measure": match_col(numeric), "aggregation": agg}

    # contextual follow-up: "what about profit?" -> reuse last op, swap measure
    if last_plan and len(q.split()) <= 5:
        new_measure = match_col(numeric)
        if new_measure:
            updated = dict(last_plan)
            updated["measure"] = new_measure
            if "measures" in updated:
                updated["measures"] = [new_measure]
            return updated

    # groupby / ranking / comparison / "by X"
    dim = match_col(categorical)
    measure = match_col(numeric) or (last_plan.get("measure") if last_plan else None) or (numeric[0] if numeric else None)
    if dim and measure:
        limit = None
        m = re.search(r"top\s+(\d+)", q)
        if m:
            limit = int(m.group(1))
        elif "top" in q:
            limit = 5
        sort = "asc" if any(w in q for w in ["lowest", "underperform", "worst", "bottom", "least"]) else "desc"
        return {"operation": "groupby", "dimension": dim, "measure": measure,
                "aggregation": "sum" if agg == "sum" else agg, "sort": sort, "limit": limit}

    # fall back to summary
    if numeric and categorical:
        return {"operation": "groupby", "dimension": categorical[0], "measure": numeric[0],
                "aggregation": "sum", "sort": "desc", "limit": 10}
    return {"operation": "summary"}


def _last_plan(recent: list[dict]) -> dict | None:
    for msg in reversed(recent):
        meta = msg.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("plan"):
            return meta["plan"]
    return None


# --------------------------------------------------------------------------- #
# Explanation
# --------------------------------------------------------------------------- #
def explain(question: str, plan: dict, result_data: dict, result_summary: str,
            used_llm: bool) -> str:
    provider = get_provider()
    if provider.available:
        try:
            compact = _compact_result(result_data)
            return provider.generate(
                prompts.EXPLAINER_SYSTEM,
                prompts.explainer_prompt(question, plan, compact),
                temperature=0.3,
            )
        except LLMUnavailable as exc:
            logger.warning("LLM explanation failed (%s); using template.", exc)
    return _template_explanation(plan, result_summary)


def _compact_result(data: dict) -> dict:
    """Trim result payloads so we never ship huge tables to the LLM."""
    out = {}
    for k, v in data.items():
        if isinstance(v, list):
            out[k] = v[:15]
        elif isinstance(v, dict):
            out[k] = {kk: (vv[:15] if isinstance(vv, list) else vv) for kk, vv in v.items()}
        else:
            out[k] = v
    return out


def _template_explanation(plan: dict, summary: str) -> str:
    op = plan.get("operation")
    base = {
        "groupby": "Here is the breakdown based on your dataset.",
        "trend": "Here is how the metric has moved over time.",
        "correlation": "Here is the correlation between the selected measures.",
        "anomaly": "Here are the unusual records detected in your data.",
        "aggregate": "Here is the computed value.",
        "compare": "Here is the comparison you asked for.",
        "chart": "Here is the chart generated from your data.",
        "summary": "Here is a summary of your dataset.",
    }.get(op, "Here is the result of your analysis.")
    return f"{base} {summary}".strip()


# --------------------------------------------------------------------------- #
# Follow-up suggestions
# --------------------------------------------------------------------------- #
def suggest_followups(question: str, plan: dict, loaded: LoadedDataset,
                      result_summary: str) -> list[dict]:
    provider = get_provider()
    if provider.available:
        try:
            raw = provider.generate(
                prompts.FOLLOWUP_SYSTEM,
                prompts.followup_prompt(question, loaded.types, result_summary),
                json_mode=True, temperature=0.6,
            )
            parsed = _extract_json(raw)
            sugg = parsed.get("suggestions", [])
            if sugg:
                return sugg[:3]
        except (LLMUnavailable, json.JSONDecodeError, ValueError):
            pass
    return heuristic_followups(plan, loaded)


def heuristic_followups(plan: dict, loaded: LoadedDataset) -> list[dict]:
    numeric = [c for c, t in loaded.types.items() if is_numeric_type(t)]
    categorical = [c for c, t in loaded.types.items() if t in ("categorical", "boolean", "text")]
    datetimes = [c for c, t in loaded.types.items() if t == "datetime"]
    s: list[dict] = []
    op = plan.get("operation")

    if op == "groupby":
        dim, measure = plan.get("dimension"), plan.get("measure")
        if datetimes and measure:
            s.append({"label": f"Monthly {measure}", "question": f"Show monthly {measure}"})
        other = next((n for n in numeric if n != measure), None)
        if other and dim:
            s.append({"label": f"{other} by {dim}", "question": f"Show {other} by {dim}"})
        s.append({"label": "Find anomalies", "question": f"Find unusual values in {measure}"})
    elif op == "trend":
        measure = plan.get("measure")
        other = next((n for n in numeric if n != measure), None)
        if other:
            s.append({"label": f"Monthly {other}", "question": f"Show monthly {other}"})
        if categorical and measure:
            s.append({"label": f"{measure} by {categorical[0]}", "question": f"Show {measure} by {categorical[0]}"})
        s.append({"label": "Find unusual months", "question": f"Find anomalies in {measure}"})
    else:
        if categorical and numeric:
            s.append({"label": f"{numeric[0]} by {categorical[0]}", "question": f"Show {numeric[0]} by {categorical[0]}"})
        if datetimes and numeric:
            s.append({"label": f"Monthly {numeric[0]}", "question": f"Show monthly {numeric[0]}"})
        if len(numeric) >= 2:
            s.append({"label": "Correlations", "question": f"What is the relationship between {numeric[0]} and {numeric[1]}?"})
    # de-dup & cap
    seen, out = set(), []
    for item in s:
        if item["question"] not in seen:
            seen.add(item["question"])
            out.append(item)
    return out[:3]
