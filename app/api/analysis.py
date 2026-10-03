from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_dataset_or_404
from app.core.database import get_db
from app.models import Dataset
from app.repositories import dataset_repo
from app.schemas.analysis import (
    DataProfile,
    ProfileRequest,
    StatisticsRequest,
    StatisticsResult,
)
from app.analytics.correlation import correlation_matrix
from app.analytics.statistics import describe_numeric
from app.ingestion.types import is_numeric_type
from app.services import data_access, profiling_service

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/profile", response_model=DataProfile)
def profile(req: ProfileRequest, db: Session = Depends(get_db)):
    ds = dataset_repo.get_dataset(db, req.dataset_id)
    if not ds or not ds.storage_path:
        raise HTTPException(404, "Dataset not found")
    return profiling_service.build_profile(ds)


@router.post("/statistics", response_model=StatisticsResult)
def statistics(req: StatisticsRequest, db: Session = Depends(get_db)):
    ds = dataset_repo.get_dataset(db, req.dataset_id)
    if not ds or not ds.storage_path:
        raise HTTPException(404, "Dataset not found")
    loaded = data_access.load_dataset(str(ds.id), ds.storage_path)
    cols = req.columns or list(loaded.types.keys())
    stats: dict[str, dict] = {}
    numeric_cols = []
    for c in cols:
        if c not in loaded.types:
            raise HTTPException(400, f"Column '{c}' does not exist.")
        if is_numeric_type(loaded.types[c]):
            numeric_cols.append(c)
            stats[c] = describe_numeric(loaded.df[c])
        else:
            vc = loaded.df[c].dropna().astype(str).value_counts().head(10)
            stats[c] = {"top_values": [{"value": k, "count": int(v)} for k, v in vc.items()]}
    corr = None
    if len(numeric_cols) >= 2:
        corr = correlation_matrix(loaded.df, numeric_cols)["matrix"]
    return StatisticsResult(dataset_id=ds.id, statistics=stats, correlations=corr)
