"""Data-access layer for datasets. All DB logic lives here, not in routes."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Dataset, DatasetColumn, DatasetSheet, Insight, Visualization


def list_datasets(db: Session) -> list[Dataset]:
    return list(db.scalars(select(Dataset).order_by(Dataset.created_at.desc())))


def get_dataset(db: Session, dataset_id: uuid.UUID) -> Dataset | None:
    return db.scalar(
        select(Dataset)
        .options(selectinload(Dataset.columns), selectinload(Dataset.sheets))
        .where(Dataset.id == dataset_id)
    )


def create_dataset(db: Session, **kwargs) -> Dataset:
    ds = Dataset(**kwargs)
    db.add(ds)
    db.flush()
    return ds


def add_columns(db: Session, dataset_id: uuid.UUID, columns: list[dict]) -> None:
    db.query(DatasetColumn).filter(DatasetColumn.dataset_id == dataset_id).delete()
    for i, c in enumerate(columns):
        db.add(DatasetColumn(dataset_id=dataset_id, position=i, **c))


def add_sheets(db: Session, dataset_id: uuid.UUID, sheets: list[dict]) -> None:
    db.query(DatasetSheet).filter(DatasetSheet.dataset_id == dataset_id).delete()
    for s in sheets:
        db.add(DatasetSheet(dataset_id=dataset_id, **s))


def get_columns(db: Session, dataset_id: uuid.UUID) -> list[DatasetColumn]:
    return list(db.scalars(
        select(DatasetColumn)
        .where(DatasetColumn.dataset_id == dataset_id)
        .order_by(DatasetColumn.position)
    ))


def replace_insights(db: Session, dataset_id: uuid.UUID, insights: list[dict]) -> list[Insight]:
    db.query(Insight).filter(Insight.dataset_id == dataset_id).delete()
    objs = [Insight(dataset_id=dataset_id, **i) for i in insights]
    db.add_all(objs)
    db.flush()
    return objs


def get_insights(db: Session, dataset_id: uuid.UUID) -> list[Insight]:
    return list(db.scalars(
        select(Insight).where(Insight.dataset_id == dataset_id).order_by(Insight.created_at)
    ))


def save_visualization(db: Session, dataset_id: uuid.UUID, chart_type: str,
                       title: str | None, configuration: dict) -> Visualization:
    v = Visualization(dataset_id=dataset_id, chart_type=chart_type,
                      title=title, configuration=configuration)
    db.add(v)
    db.flush()
    return v
