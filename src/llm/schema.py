from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.shared.paths import mart_data_path

MART_COLUMNS: dict[str, str] = {
    "timestamp": "datetime, ISO with timezone",
    "Price ($/MWh)": "float, market price, may be NaN",
    "Demand (MW)": "float, system demand, may be NaN",
    "facility_code": "str, unique facility id",
    "Power (MW)": "float, facility output, negatives already cleaned to 0",
    "Emissions (tonnes)": "float, may be NaN",
    "facility_name": "str",
    "lat": "float",
    "lng": "float",
    "state": "str, AU state code",
    "fuel_list": "str, Python-list-like e.g. \"['Wind', 'Gas']\"",
}


def schema_json() -> str:
    return json.dumps(MART_COLUMNS, indent=2)


def sample_rows_json(df: pd.DataFrame, n: int = 3) -> str:
    sample = df.head(n).copy()
    if "timestamp" in sample.columns:
        sample["timestamp"] = sample["timestamp"].astype(str)
    return sample.to_json(orient="records", indent=2)


def load_mart_dataframe(
    max_rows: int,
    data_path: Path | None = None,
) -> pd.DataFrame:
    path = data_path or mart_data_path("data_for_publish.csv")
    if not path.exists():
        raise FileNotFoundError(
            f"Mart data file not found: {path}. "
            "Run the publisher pipeline to generate data/mart/data_for_publish.csv."
        )

    df = pd.read_csv(path, nrows=max_rows)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


__all__ = [
    "MART_COLUMNS",
    "load_mart_dataframe",
    "sample_rows_json",
    "schema_json",
]
