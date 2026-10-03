from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.visualization import VisualizationResult

ResponseType = Literal["text", "table", "kpi", "visualization", "analysis", "error", "clarification"]


class ConversationCreate(BaseModel):
    dataset_id: UUID | None = None
    title: str | None = None


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ConversationOut(BaseModel):
    """Lightweight conversation record for the sidebar (no messages)."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    dataset_id: UUID | None
    dataset_name: str | None = None
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    role: str
    content: str
    metadata: dict[str, Any] = {}
    created_at: datetime


class SuggestedQuestion(BaseModel):
    label: str
    question: str


class AssistantRequest(BaseModel):
    dataset_id: UUID
    session_id: UUID | None = None
    message: str


class KpiCard(BaseModel):
    label: str
    value: str
    delta: str | None = None
    trend: str | None = None  # up | down | flat


class AssistantResponse(BaseModel):
    session_id: UUID
    message: str
    response_type: ResponseType = "text"
    data: dict[str, Any] = {}
    kpis: list[KpiCard] = []
    visualization: VisualizationResult | None = None
    suggested_questions: list[SuggestedQuestion] = []
    plan: dict[str, Any] | None = None
    ai_available: bool = True
