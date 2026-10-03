"""Dispatch raw files to the right ingestion backend."""
from __future__ import annotations

import os

import pandas as pd

from app.ingestion.csv import load_csv
from app.ingestion.excel import load_excel
from app.ingestion.pdf import load_pdf

EXCEL_EXT = {".xlsx", ".xls", ".xlsm"}


def extension_of(filename: str) -> str:
    return os.path.splitext(filename)[1].lower().lstrip(".")


def load_file(path: str) -> dict:
    """Return {sheets: {name: DataFrame}} for any supported file."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return load_csv(path)
    if ext in EXCEL_EXT:
        return load_excel(path)
    if ext == ".pdf":
        return load_pdf(path)
    raise ValueError(f"Unsupported file type: {ext}")


def primary_sheet(sheets: dict[str, pd.DataFrame]) -> tuple[str, pd.DataFrame]:
    """Pick the largest sheet as the analytics-primary table."""
    name = max(sheets, key=lambda k: sheets[k].shape[0] * sheets[k].shape[1])
    return name, sheets[name]
