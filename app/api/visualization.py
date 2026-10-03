from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Dataset
from app.repositories import dataset_repo
from app.schemas.visualization import VisualizationConfig, VisualizationResult
from app.services import data_access
from app.visualization.engine import VisualizationError, build_visualization

router = APIRouter(prefix="/visualizations", tags=["visualization"])


@router.post("/preview", response_model=VisualizationResult)
def preview_visualization(cfg: VisualizationConfig, db: Session = Depends(get_db)):
    ds = dataset_repo.get_dataset(db, cfg.dataset_id)
    if not ds or not ds.storage_path:
        raise HTTPException(404, "Dataset not found")
    loaded = data_access.load_dataset(str(ds.id), ds.storage_path)
    try:
        result = build_visualization(cfg, loaded)
    except VisualizationError as exc:
        raise HTTPException(400, str(exc)) from exc
    # persist the configuration for reuse
    dataset_repo.save_visualization(db, ds.id, result.chart_type, result.title,
                                    cfg.model_dump(mode="json"))
    db.commit()
    return result
