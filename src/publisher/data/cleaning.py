from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.shared.paths import staging_data_path


def normalize_non_negative(series: pd.Series) -> pd.Series:
    """Replace negative values with 0 while preserving NaN for true missing data."""
    return series.mask(series < 0, 0)


def fill_missing_half_ffill_bfill(series: pd.Series) -> pd.Series:
    """
    Vectorized processing for missing values in a single column:
    - For continuous missing segments: Fill first half with ffill, second half with bfill.
    - Keep fully missing segments as NaN (do not fill with 0).
    """
    non_na = series.notna()
    missing = ~non_na
    original_index = series.index

    if series.isna().all():
        return series.copy()

    segment_id = non_na.cumsum()
    segment_id_missing = segment_id.where(missing, np.nan)

    within_segment_idx = (
        segment_id_missing.groupby(segment_id_missing)
        .transform(lambda x: np.arange(1, len(x) + 1))
        .reindex(original_index, fill_value=np.nan)
    )

    segment_length = (
        segment_id_missing.groupby(segment_id_missing)
        .transform("count")
        .reindex(original_index, fill_value=np.nan)
    )

    ffill_series = series.ffill()
    bfill_series = series.bfill()
    is_first_half = (within_segment_idx <= (segment_length // 2)) & missing

    filled_values = np.where(
        non_na,
        series,
        np.where(is_first_half, ffill_series, bfill_series),
    )
    return pd.Series(filled_values, index=original_index, name=series.name)


def handle_missing_values_fast(group: pd.DataFrame) -> pd.DataFrame:
    """
    Fast missing value handling for a single facility's data:
    - Strictly exclude facilities with full missing values (both Power and Emissions are all NaN).
    - Only process missing values for non-full-missing facilities.
    """
    power_all_na = group["Power (MW)"].isna().all()
    emission_all_na = group["Emissions (tonnes)"].isna().all()

    if power_all_na and emission_all_na:
        return pd.DataFrame()

    group = group.copy()
    group["Power (MW)"] = fill_missing_half_ffill_bfill(group["Power (MW)"])
    group["Emissions (tonnes)"] = fill_missing_half_ffill_bfill(
        group["Emissions (tonnes)"]
    )
    return group


def clean_facility_list(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    if "facility_code" in cleaned.columns:
        cleaned["facility_code"] = cleaned["facility_code"].astype("string").str.strip()
    if "facility_name" in cleaned.columns:
        cleaned["facility_name"] = cleaned["facility_name"].astype("string").str.strip()
    for column in ("lat", "lng"):
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    subset = [
        column
        for column in ("facility_code", "facility_name")
        if column in cleaned.columns
    ]
    if subset:
        cleaned = cleaned.drop_duplicates(subset=subset, keep="last")
    return cleaned.reset_index(drop=True)


def clean_consolidated_data(
    input_path,
    output_path,
) -> pd.DataFrame:
    output_path = (
        Path(output_path)
        if output_path is not None
        else staging_data_path("open_electricity", "consolidated_data_cleaned.csv")
    )
    data = pd.read_csv(input_path)
    if "facility_code" in data.columns:
        data["facility_code"] = data["facility_code"].astype("string").str.strip()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=False)
    for column in ("Power (MW)", "Emissions (tonnes)", "Price ($/MWh)", "Demand (MW)"):
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    data["Power (MW)"] = normalize_non_negative(data["Power (MW)"])
    data["Emissions (tonnes)"] = normalize_non_negative(data["Emissions (tonnes)"])
    data = data.drop_duplicates(
        subset=[
            column
            for column in ("facility_code", "timestamp")
            if column in data.columns
        ],
        keep="last",
    )
    data = data.groupby("facility_code", group_keys=False, observed=True).apply(
        handle_missing_values_fast,
        include_groups=False,
    )
    df_cleaned = data.dropna(how="all")
    if not df_cleaned.empty and {"facility_code", "timestamp"}.issubset(
        df_cleaned.columns
    ):
        df_cleaned = df_cleaned.sort_values(["facility_code", "timestamp"]).reset_index(
            drop=True
        )
        df_cleaned = df_cleaned.drop_duplicates(
            subset=["facility_code", "timestamp"], keep="last"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_cleaned.to_csv(output_path, index=False)
    return df_cleaned
