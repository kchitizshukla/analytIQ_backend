"""CSV ingestion with delimiter + header detection."""
from __future__ import annotations

import csv as _csv
import io

import pandas as pd

from app.ingestion.tables import clean_dataframe


def _sniff_delimiter(sample: str) -> str:
    try:
        dialect = _csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except Exception:
        # fall back to the most frequent candidate on the first line
        first = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: first.count(d) for d in [",", ";", "\t", "|"]}
        return max(counts, key=counts.get) if any(counts.values()) else ","


def load_csv(path: str) -> dict:
    """Load a CSV file. Returns {sheets: {name: DataFrame}}."""
    with open(path, "rb") as fh:
        raw_bytes = fh.read()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw_bytes.decode("utf-8", errors="replace")

    delimiter = _sniff_delimiter(text[:8192])
    df = pd.read_csv(io.StringIO(text), sep=delimiter, engine="python", skip_blank_lines=True)
    df = clean_dataframe(df)
    return {"sheets": {"Sheet1": df}}
