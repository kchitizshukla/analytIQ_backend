from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InsightItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID | None = None
    insight_type: str
    title: str
    description: str
    data: dict[str, Any] = {}
    severity: str = "info"
    created_at: datetime | None = None


class InsightsResponse(BaseModel):
    dataset_id: UUID
    generated_with_ai: bool
    insights: list[InsightItem]
