from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_dataset_or_404
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import api_error
from app.ingestion.loader import extension_of
from app.models import Dataset
from app.repositories import dataset_repo
from app.schemas.dataset import (
    ColumnInfo,
    ColumnsResponse,
    DatasetDetail,
    DatasetPreview,
    DatasetSummary,
)
from app.services import ingestion_service, profiling_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=list[DatasetSummary])
def list_datasets(db: Session = Depends(get_db)):
    return dataset_repo.list_datasets(db)


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(ds: Dataset = Depends(get_dataset_or_404)):
    return DatasetDetail(
        id=ds.id, name=ds.name, original_filename=ds.original_filename,
        file_type=ds.file_type, file_size=ds.file_size, row_count=ds.row_count,
        column_count=ds.column_count, status=ds.status, created_at=ds.created_at,
        updated_at=ds.updated_at, error_message=ds.error_message,
        columns=[_col(c) for c in ds.columns],
        sheets=[{"sheet_name": s.sheet_name, "row_count": s.row_count,
                 "column_count": s.column_count} for s in ds.sheets],
    )


@router.get("/{dataset_id}/columns", response_model=ColumnsResponse)
def get_columns(ds: Dataset = Depends(get_dataset_or_404), db: Session = Depends(get_db)):
    cols = dataset_repo.get_columns(db, ds.id)
    return ColumnsResponse(dataset_id=ds.id, columns=[_col(c) for c in cols])


@router.get("/{dataset_id}/preview", response_model=DatasetPreview)
def preview(ds: Dataset = Depends(get_dataset_or_404),
            page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)):
    return profiling_service.build_preview(ds, page=page, page_size=page_size)


# Media types for serving the original uploaded file back to the user.
_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "pdf": "application/pdf",
}


@router.get("/{dataset_id}/download")
def download(ds: Dataset = Depends(get_dataset_or_404)):
    """Stream the original uploaded file back with its original filename."""
    if not ds.storage_path or not os.path.isfile(ds.storage_path):
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "FILE_NOT_FOUND",
            "The original file for this dataset is no longer available.",
        )
    media_type = _MEDIA_TYPES.get(ds.file_type, "application/octet-stream")
    return FileResponse(
        ds.storage_path,
        media_type=media_type,
        filename=ds.original_filename,
    )


@router.post("/upload", response_model=DatasetDetail, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile = File(...), name: str | None = Form(None),
                 db: Session = Depends(get_db)):
    ext = extension_of(file.filename or "")
    if ext not in settings.allowed_extensions:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unsupported file type '.{ext}'. Allowed: "
                            f"{', '.join(settings.allowed_extensions)}")
    contents = await file.read()
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"File exceeds {settings.max_upload_size_mb} MB limit.")
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty.")

    storage_path, file_type = ingestion_service.save_upload(contents, file.filename)
    dataset_name = name or os.path.splitext(file.filename)[0]
    try:
        dataset_id = ingestion_service.ingest_dataset(
            db, name=dataset_name, original_filename=file.filename,
            storage_path=storage_path, file_type=file_type, file_size=len(contents),
        )
    except Exception as exc:
        # clean up the stored file on failure
        try:
            os.remove(storage_path)
        except OSError:
            pass
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Unable to process this file: {exc}") from exc

    ds = dataset_repo.get_dataset(db, dataset_id)
    return get_dataset(ds)


def _col(c) -> ColumnInfo:
    return ColumnInfo(
        name=c.column_name, type=c.inferred_type, nullable=c.nullable,
        unique_count=c.unique_count, null_count=c.null_count,
        sample_values=c.sample_values or [], stats=c.stats or {},
    )
