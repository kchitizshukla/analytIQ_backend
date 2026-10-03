"""Generate the deterministic 'Sales Analytics 2026' demo dataset.

Writes an .xlsx and .csv into UPLOAD_DIR with a FIXED dataset id so the SQL seed
(database/insert_dummy_data.sql) can reference the same file. Realistic
relationships: revenue depends on quantity x price; profit = revenue - cost;
discount affects profit. A few intentional anomalies are injected.

Run:  backend/.venv/bin/python -m scripts.generate_demo_dataset
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

# Fixed id shared with insert_dummy_data.sql
DEMO_DATASET_ID = "a1b2c3d4-0000-4000-8000-000000000001"
SEED = 2026

PRODUCTS = {
    "Electronics": [("Laptop Pro", 1200), ("Smartphone X", 800), ("Wireless Earbuds", 150),
                    ("4K Monitor", 400), ("Mechanical Keyboard", 120)],
    "Home & Kitchen": [("Air Fryer", 130), ("Coffee Maker", 90), ("Vacuum Robot", 350),
                       ("Blender Max", 70)],
    "Apparel": [("Running Shoes", 110), ("Winter Jacket", 180), ("Cotton T-Shirt", 25)],
    "Office": [("Standing Desk", 450), ("Ergo Chair", 320), ("Desk Lamp", 45)],
}
REGIONS = ["North", "South", "East", "West", "Central"]
CUSTOMERS = [f"Customer {i:03d}" for i in range(1, 61)]


def generate(rows: int = 2400) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    cats = list(PRODUCTS.keys())
    dates = pd.date_range("2026-01-01", "2026-12-31", freq="D")

    records = []
    for _ in range(rows):
        category = rng.choice(cats, p=[0.42, 0.25, 0.18, 0.15])
        product, base_price = PRODUCTS[category][rng.integers(len(PRODUCTS[category]))]
        region = rng.choice(REGIONS, p=[0.28, 0.22, 0.2, 0.18, 0.12])
        customer = rng.choice(CUSTOMERS)
        date = rng.choice(dates)

        # seasonal lift towards year end
        month = pd.Timestamp(date).month
        season = 1.0 + 0.04 * month + (0.25 if month in (11, 12) else 0.0)

        quantity = int(max(1, rng.poisson(4) + 1))
        unit_price = round(base_price * rng.uniform(0.92, 1.08), 2)
        revenue = round(quantity * unit_price * season, 2)
        discount = round(float(rng.choice([0, 0.05, 0.1, 0.15, 0.2],
                                          p=[0.45, 0.25, 0.15, 0.1, 0.05])), 2)
        revenue_net = round(revenue * (1 - discount), 2)
        cost = round(revenue_net * rng.uniform(0.55, 0.78), 2)
        profit = round(revenue_net - cost, 2)

        records.append({
            "Date": pd.Timestamp(date).strftime("%Y-%m-%d"),
            "Product": product,
            "Category": category,
            "Region": region,
            "Customer": customer,
            "Quantity": quantity,
            "Revenue": revenue_net,
            "Cost": cost,
            "Profit": profit,
            "Discount": discount,
        })

    df = pd.DataFrame(records).sort_values("Date").reset_index(drop=True)

    # --- inject intentional anomalies ---
    idx = rng.choice(df.index, size=8, replace=False)
    df.loc[idx[:4], "Revenue"] = df.loc[idx[:4], "Revenue"] * rng.uniform(6, 10, size=4)
    df.loc[idx[:4], "Profit"] = df.loc[idx[:4], "Revenue"] * 0.3
    df.loc[idx[4:6], "Quantity"] = df.loc[idx[4:6], "Quantity"] * 25
    df.loc[idx[6:], "Profit"] = -df.loc[idx[6:], "Cost"] * 0.5  # loss-making outliers
    df["Revenue"] = df["Revenue"].round(2)
    df["Profit"] = df["Profit"].round(2)
    return df


def main() -> None:
    upload_dir = os.environ.get("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads"))
    upload_dir = os.path.abspath(upload_dir)
    os.makedirs(upload_dir, exist_ok=True)

    df = generate()
    xlsx_path = os.path.join(upload_dir, f"{DEMO_DATASET_ID.replace('-', '')}.xlsx")
    csv_path = os.path.join(upload_dir, f"{DEMO_DATASET_ID.replace('-', '')}.csv")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="Sales 2026")
    df.to_csv(csv_path, index=False)

    # also drop a copy with a friendly name for the "upload this file" demo step
    friendly = os.path.join(upload_dir, "Sales_Analytics_2026.xlsx")
    with pd.ExcelWriter(friendly, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="Sales 2026")

    print(f"rows={len(df)} cols={len(df.columns)}")
    print(f"xlsx={xlsx_path}")
    print(f"csv={csv_path}")
    print(f"friendly={friendly}")
    print("unique:", {c: int(df[c].nunique()) for c in df.columns})


if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    main()
