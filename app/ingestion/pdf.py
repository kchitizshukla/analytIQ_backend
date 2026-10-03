"""PDF table extraction.

Targets text-based / tabular PDFs via PyMuPDF's table finder. OCR for scanned
PDFs is intentionally left as an extension point (see _needs_ocr).
"""
from __future__ import annotations

import pandas as pd

from app.ingestion.tables import clean_dataframe


def _needs_ocr(page) -> bool:
    """Extension point: a page with no extractable text likely needs OCR."""
    return not page.get_text("text").strip()


def load_pdf(path: str) -> dict:
    """Extract tables from a PDF. Returns {sheets: {name: DataFrame}}."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyMuPDF (fitz) is required for PDF ingestion") from exc

    doc = fitz.open(path)
    sheets: dict[str, pd.DataFrame] = {}
    table_idx = 0
    ocr_pages = 0

    for page_number, page in enumerate(doc, start=1):
        if _needs_ocr(page):
            ocr_pages += 1
            continue
        try:
            found = page.find_tables()
        except Exception:
            continue
        for tbl in found.tables:
            try:
                rows = tbl.extract()
            except Exception:
                continue
            if not rows or len(rows) < 2:
                continue
            header, *body = rows
            df = pd.DataFrame(body, columns=header)
            df = clean_dataframe(df)
            if df.empty or len(df.columns) == 0:
                continue
            table_idx += 1
            sheets[f"Page{page_number}_Table{table_idx}"] = df

    doc.close()

    if not sheets:
        hint = " The document appears to be scanned; OCR is not enabled." if ocr_pages else ""
        raise ValueError(f"No tables could be extracted from this PDF.{hint}")

    return {"sheets": sheets}
