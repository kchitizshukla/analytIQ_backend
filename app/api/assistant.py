from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import api_error
from app.models import ChatSession, User
from app.repositories import chat_repo, dataset_repo
from app.schemas.assistant import (
    AssistantRequest,
    AssistantResponse,
    ChatMessageOut,
    ConversationCreate,
    ConversationOut,
    ConversationRename,
)
from app.services import assistant_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


# --------------------------------------------------------------------------- #
# Ownership helpers
# --------------------------------------------------------------------------- #
def _owned_conversation(db: Session, user: User, conversation_id: uuid.UUID) -> ChatSession:
    """Return the conversation iff it belongs to the authenticated user.

    Returns a uniform 404 for both missing and not-owned so we never reveal the
    existence of another user's conversation.
    """
    session = chat_repo.get_session(db, conversation_id)
    if not session or session.user_id != user.id:
        raise api_error(status.HTTP_404_NOT_FOUND, "CONVERSATION_NOT_FOUND", "Conversation not found.")
    return session


def _dataset_name(db: Session, dataset_id: uuid.UUID | None) -> str | None:
    if not dataset_id:
        return None
    ds = dataset_repo.get_dataset(db, dataset_id)
    return ds.name if ds else None


def _to_out(session: ChatSession, dataset_name: str | None) -> ConversationOut:
    return ConversationOut(
        id=session.id, dataset_id=session.dataset_id, dataset_name=dataset_name,
        title=session.title, created_at=session.created_at, updated_at=session.updated_at,
    )


# --------------------------------------------------------------------------- #
# Conversation CRUD
# --------------------------------------------------------------------------- #
@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    dataset_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = chat_repo.list_sessions_for_user(db, user.id, dataset_id)
    return [_to_out(s, name) for s, name in rows]


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.dataset_id and not dataset_repo.get_dataset(db, body.dataset_id):
        raise api_error(status.HTTP_404_NOT_FOUND, "DATASET_NOT_FOUND", "Dataset not found.")
    session = chat_repo.create_session(db, body.dataset_id, user.id, body.title or "New conversation")
    db.commit()
    return _to_out(session, _dataset_name(db, session.dataset_id))


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _owned_conversation(db, user, conversation_id)
    return _to_out(session, _dataset_name(db, session.dataset_id))


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationRename,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _owned_conversation(db, user, conversation_id)
    session.title = body.title.strip()
    db.commit()
    db.refresh(session)
    return _to_out(session, _dataset_name(db, session.dataset_id))


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _owned_conversation(db, user, conversation_id)
    chat_repo.delete_session(db, session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageOut])
def get_conversation_messages(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _owned_conversation(db, user, conversation_id)
    return [
        ChatMessageOut(id=m.id, role=m.role, content=m.content,
                       metadata=m.metadata_ or {}, created_at=m.created_at)
        for m in chat_repo.get_messages(db, conversation_id)
    ]


# --------------------------------------------------------------------------- #
# Chat (analytics + AI pipeline)
# --------------------------------------------------------------------------- #
@router.post("/chat", response_model=AssistantResponse)
def chat(
    req: AssistantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if req.session_id:
        # Continuing an existing conversation: the conversation's own dataset is
        # authoritative — never trust whichever dataset the frontend sends.
        session = _owned_conversation(db, user, req.session_id)
        ds = dataset_repo.get_dataset(db, session.dataset_id) if session.dataset_id else None
    else:
        ds = dataset_repo.get_dataset(db, req.dataset_id)
    if not ds or not ds.storage_path:
        raise api_error(status.HTTP_404_NOT_FOUND, "DATASET_NOT_FOUND", "Dataset not found.")

    session_id = assistant_service.ensure_session(db, ds.id, req.session_id, req.message, user.id)
    return assistant_service.chat(db, ds, session_id, req.message)
