from __future__ import annotations

from pathlib import Path

import pandas as pd

from .facility_metadata import load_facility_metadata_csv


def combine_matching(
    df1: pd.DataFrame, df2: pd.DataFrame, left_on: str, right_on: str, keep: bool
) -> pd.DataFrame:
    df2 = df2.drop(columns=["lat", "lng"], errors="ignore")
    matches = []
    for idx1, row1 in df1.iterrows():
        matched_df2 = df2[df2[right_on].str.contains(row1[left_on], na=False)]
        if not matched_df2.empty:
            for idx2 in matched_df2.index:
                matches.append({"df1_idx": idx1, "df2_idx": idx2})
        elif keep:
            matches.append({"df1_idx": idx1, "df2_idx": None})

    if not matches:
        return pd.DataFrame(columns=list(df1.columns) + list(df2.columns))

    match_df = pd.DataFrame(matches)
    result = pd.merge(
        match_df,
        df1.reset_index().rename(columns={"index": "df1_idx"}),
        on="df1_idx",
        how="left",
    ).merge(
        df2.reset_index().rename(columns={"index": "df2_idx"}),
        on="df2_idx",
        how="left",
    )
    return result.drop(columns=["df1_idx", "df2_idx"])


def combine_fuels(group: pd.DataFrame) -> list:
    fuel_list = group["primaryFuel"].tolist()
    future_fuels = group["futureFuelSource"].dropna().tolist()
    fuel_list.extend(future_fuels)
    return fuel_list


def build_publish_dataset(
    cleaned_data_path,
    facility_list_path,
    nger_path,
    cer_path,
    output_path,
) -> pd.DataFrame:
    output_path = Path(output_path)
    df_cleaned = pd.read_csv(cleaned_data_path)
    df1 = pd.read_csv(facility_list_path)
    df2 = load_facility_metadata_csv(nger_path)
    df3 = load_facility_metadata_csv(cer_path)

    tmp_df = combine_matching(
        df1, df2, left_on="facility_name", right_on="facilityName", keep=False
    )
    tmp_df2 = combine_matching(
        tmp_df, df3, left_on="facility_name", right_on="powerStation", keep=True
    )
    tmp_df3 = tmp_df2[
        [
            "facility_code",
            "facility_name",
            "primaryFuel",
            "state_x",
            "lat",
            "lng",
            "fuelSource",
        ]
    ]
    tmp_df3 = tmp_df3.rename(
        columns={"state_x": "state", "fuelSource": "futureFuelSource"}
    )
    tmp_df3_clean = tmp_df3.drop_duplicates()

    grouped = (
        tmp_df3_clean.groupby(["facility_name", "facility_code", "lat", "lng", "state"])
        .apply(combine_fuels, include_groups=False)
        .reset_index(name="fuel_list")
    )

    merged_df = pd.merge(df_cleaned, grouped, on="facility_code", how="inner")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(output_path, index=False)
    return merged_df


__all__ = ["combine_matching", "combine_fuels", "build_publish_dataset"]
