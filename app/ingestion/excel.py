"""Excel ingestion (.xlsx / .xls) with multi-sheet + header detection."""
from __future__ import annotations

import pandas as pd

from app.ingestion.tables import clean_dataframe, detect_header_row


def load_excel(path: str) -> dict:
    """Load an Excel workbook. Returns {sheets: {sheet_name: DataFrame}}."""
    engine = "openpyxl" if path.lower().endswith("x") else None
    xls = pd.ExcelFile(path, engine=engine)
    sheets: dict[str, pd.DataFrame] = {}

    for sheet_name in xls.sheet_names:
        raw = xls.parse(sheet_name, header=None)
        if raw.empty:
            continue
        header_row = detect_header_row(raw)
        df = xls.parse(sheet_name, header=header_row)
        df = clean_dataframe(df)
        if not df.empty and len(df.columns) > 0:
            sheets[str(sheet_name)] = df

    if not sheets:
        # fall back to a naive parse of the first sheet
        df = clean_dataframe(xls.parse(xls.sheet_names[0]))
        sheets[str(xls.sheet_names[0])] = df

    return {"sheets": sheets}
