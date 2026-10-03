"""Data-access layer for chat sessions & messages."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession, Dataset


def create_session(db: Session, dataset_id: uuid.UUID | None, user_id: uuid.UUID | None,
                   title: str) -> ChatSession:
    s = ChatSession(dataset_id=dataset_id, user_id=user_id, title=title)
    db.add(s)
    db.flush()
    return s


def list_sessions_for_user(
    db: Session, user_id: uuid.UUID, dataset_id: uuid.UUID | None = None
) -> list[tuple[ChatSession, str | None]]:
    """Lightweight conversation list for the sidebar: (session, dataset_name).

    Scoped to the owning user and ordered by most recently updated.
    """
    stmt = (
        select(ChatSession, Dataset.name)
        .outerjoin(Dataset, Dataset.id == ChatSession.dataset_id)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    if dataset_id:
        stmt = stmt.where(ChatSession.dataset_id == dataset_id)
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def get_session(db: Session, session_id: uuid.UUID) -> ChatSession | None:
    return db.scalar(select(ChatSession).where(ChatSession.id == session_id))


def delete_session(db: Session, session: ChatSession) -> None:
    # Cascades to chat_messages (FK ON DELETE CASCADE + ORM cascade).
    db.delete(session)


def get_messages(db: Session, session_id: uuid.UUID, limit: int | None = None) -> list[ChatMessage]:
    stmt = (select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at))
    msgs = list(db.scalars(stmt))
    return msgs[-limit:] if limit else msgs


def add_message(db: Session, session_id: uuid.UUID, role: str, content: str,
                metadata: dict | None = None) -> ChatMessage:
    m = ChatMessage(session_id=session_id, role=role, content=content, metadata_=metadata or {})
    db.add(m)
    db.flush()
    return m


def touch_session(db: Session, session: ChatSession, title: str | None = None) -> None:
    from sqlalchemy import func
    session.updated_at = func.now()
    if title:
        session.title = title
