from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories import dataset_repo
from app.schemas.insight import InsightItem, InsightsResponse
from app.services import insight_service

router = APIRouter(prefix="/insights", tags=["insights"])


class InsightsRequest(BaseModel):
    dataset_id: str
    refresh: bool = False


@router.post("/generate", response_model=InsightsResponse)
def generate(req: InsightsRequest, db: Session = Depends(get_db)):
    import uuid
    try:
        did = uuid.UUID(req.dataset_id)
    except ValueError:
        raise HTTPException(400, "Invalid dataset id")
    ds = dataset_repo.get_dataset(db, did)
    if not ds or not ds.storage_path:
        raise HTTPException(404, "Dataset not found")

    existing = dataset_repo.get_insights(db, ds.id)
    if existing and not req.refresh:
        return InsightsResponse(
            dataset_id=ds.id, generated_with_ai=False,
            insights=[InsightItem(id=i.id, insight_type=i.insight_type, title=i.title,
                                  description=i.description, data=i.data, severity=i.severity,
                                  created_at=i.created_at) for i in existing],
        )
    items, used_ai = insight_service.generate_insights(db, ds)
    return InsightsResponse(
        dataset_id=ds.id, generated_with_ai=used_ai,
        insights=[InsightItem(**i) for i in items],
    )
