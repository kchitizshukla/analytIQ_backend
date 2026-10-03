"""AI Assistant chat pipeline with persistence + context.

  user message
    -> plan (LLM or heuristic)
    -> validate + execute (deterministic query engine)
    -> explain (LLM or template)
    -> follow-ups
  All messages persisted; only recent, compact context is sent to the LLM.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.ai import analyst
from app.ai.provider import get_provider
from app.ai.query_engine import PlanError, execute_plan
from app.core.logging import get_logger
from app.models import Dataset
from app.repositories import chat_repo
from app.schemas.assistant import AssistantResponse, SuggestedQuestion
from app.services import data_access
from app.visualization.engine import VisualizationError

logger = get_logger("assistant_service")

_HISTORY_LIMIT = 8  # how many recent messages to use as context


def _recent_context(db: Session, session_id: uuid.UUID) -> list[dict]:
    msgs = chat_repo.get_messages(db, session_id, limit=_HISTORY_LIMIT)
    return [{"role": m.role, "content": m.content, "metadata": m.metadata_} for m in msgs]


def ensure_session(db: Session, dataset_id: uuid.UUID, session_id: uuid.UUID | None,
                   first_message: str, user_id: uuid.UUID | None = None) -> uuid.UUID:
    """Return the conversation id, creating it (owned by user_id) on first use.

    Callers must verify ownership of an existing session_id before calling.
    """
    if session_id:
        session = chat_repo.get_session(db, session_id)
        if session:
            return session.id
    title = analyst.generate_title(first_message)
    session = chat_repo.create_session(db, dataset_id, user_id, title)
    db.commit()
    return session.id


def chat(db: Session, dataset: Dataset, session_id: uuid.UUID, message: str) -> AssistantResponse:
    loaded = data_access.load_dataset(str(dataset.id), dataset.storage_path)
    recent = _recent_context(db, session_id)

    # persist user message first
    chat_repo.add_message(db, session_id, "user", message)
    db.commit()

    plan, used_llm = analyst.plan_question(message, loaded, recent)

    # ---- validate + execute (deterministic, safety boundary) ----
    try:
        outcome = execute_plan(plan, loaded, dataset.id)
    except (PlanError, VisualizationError) as exc:
        logger.info("Plan rejected (%s). Attempting heuristic repair.", exc)
        try:
            repaired = analyst.heuristic_plan(message, loaded, recent)
            outcome = execute_plan(repaired, loaded, dataset.id)
            plan = repaired
        except (PlanError, VisualizationError) as exc2:
            text = (f"I couldn't run that analysis: {exc2}. "
                    "Try naming a specific column, e.g. a measure and a category.")
            resp = AssistantResponse(
                session_id=session_id, message=text, response_type="error",
                suggested_questions=_as_sq(analyst.heuristic_followups({}, loaded)),
                ai_available=get_provider().available,
            )
            chat_repo.add_message(db, session_id, "assistant", text,
                                  {"error": str(exc2), "plan": plan})
            db.commit()
            return resp

    # ---- explanation ----
    if outcome.response_type == "clarification":
        text = outcome.data.get("question", "Could you clarify your question?")
        options = outcome.data.get("options", [])
        resp = AssistantResponse(
            session_id=session_id, message=text, response_type="clarification",
            data={"options": options}, plan=plan, ai_available=get_provider().available,
            suggested_questions=[SuggestedQuestion(label=o, question=o) for o in options],
        )
        chat_repo.add_message(db, session_id, "assistant", text,
                              {"plan": plan, "options": options})
        db.commit()
        return resp

    explanation = analyst.explain(message, plan, outcome.data, outcome.result_summary, used_llm)
    followups = analyst.suggest_followups(message, plan, loaded, outcome.result_summary)

    resp = AssistantResponse(
        session_id=session_id,
        message=explanation,
        response_type=outcome.response_type,
        data=outcome.data,
        kpis=outcome.kpis,
        visualization=outcome.visualization,
        suggested_questions=_as_sq(followups),
        plan=plan,
        ai_available=get_provider().available,
    )

    # persist assistant message with full metadata for context + replay
    chat_repo.add_message(
        db, session_id, "assistant", explanation,
        {
            "plan": plan,
            "response_type": outcome.response_type,
            "visualization": resp.visualization.model_dump(mode="json") if resp.visualization else None,
            "kpis": [k.model_dump() for k in outcome.kpis],
            "data": _trim(outcome.data),
            "suggested_questions": [s.model_dump() for s in resp.suggested_questions],
        },
    )
    session = chat_repo.get_session(db, session_id)
    if session:
        chat_repo.touch_session(db, session)
    db.commit()
    return resp


def _as_sq(items: list[dict]) -> list[SuggestedQuestion]:
    return [SuggestedQuestion(label=i.get("label", i.get("question", "")),
                              question=i.get("question", "")) for i in items]


def _trim(data: dict) -> dict:
    """Keep stored metadata compact."""
    out = {}
    for k, v in data.items():
        if isinstance(v, list):
            out[k] = v[:50]
        else:
            out[k] = v
    return out
