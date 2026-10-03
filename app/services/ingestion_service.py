"""Orchestrates upload -> parse -> profile -> persist."""
from __future__ import annotations

import os
import uuid
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.loader import extension_of, load_file, primary_sheet
from app.ingestion.types import coerce_column, profile_dataframe_types
from app.repositories import dataset_repo
from app.services import data_access

logger = get_logger("ingestion_service")


def _samples(series: pd.Series, n: int = 5) -> list[Any]:
    vals = series.dropna().unique()[:n]
    out = []
    for v in vals:
        if isinstance(v, (np.integer,)):
            out.append(int(v))
        elif isinstance(v, (np.floating, float)):
            out.append(round(float(v), 4))
        elif isinstance(v, (pd.Timestamp,)):
            out.append(v.isoformat())
        else:
            out.append(str(v))
    return out


def save_upload(contents: bytes, original_filename: str) -> tuple[str, str]:
    """Persist raw upload to disk, return (storage_path, file_type)."""
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = extension_of(original_filename)
    dataset_id = uuid.uuid4().hex
    safe_name = f"{dataset_id}.{ext}"
    path = os.path.join(settings.upload_dir, safe_name)
    with open(path, "wb") as fh:
        fh.write(contents)
    return path, ext


def ingest_dataset(db: Session, *, name: str, original_filename: str,
                   storage_path: str, file_type: str, file_size: int) -> uuid.UUID:
    """Parse a stored file, profile it, and persist dataset metadata + columns."""
    result = load_file(storage_path)
    sheets = result["sheets"]
    sheet_name, primary = primary_sheet(sheets)
    types = profile_dataframe_types(primary)

    ds = dataset_repo.create_dataset(
        db,
        name=name,
        original_filename=original_filename,
        file_type=file_type,
        file_size=file_size,
        storage_path=storage_path,
        row_count=int(len(primary)),
        column_count=int(len(primary.columns)),
        status="ready",
    )

    columns = []
    for col in primary.columns:
        series = primary[col]
        t = types[str(col)]
        columns.append({
            "column_name": str(col),
            "inferred_type": t,
            "nullable": bool(series.isna().any()),
            "unique_count": int(series.dropna().nunique()),
            "null_count": int(series.isna().sum()),
            "sample_values": _samples(series),
            "stats": {},
        })
    dataset_repo.add_columns(db, ds.id, columns)

    dataset_repo.add_sheets(db, ds.id, [
        {"sheet_name": sn, "row_count": int(len(df)), "column_count": int(len(df.columns))}
        for sn, df in sheets.items()
    ])

    db.commit()
    logger.info("Ingested dataset %s (%s rows, %s cols)", ds.id, len(primary), len(primary.columns))
    return ds.id
