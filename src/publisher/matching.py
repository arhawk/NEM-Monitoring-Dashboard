from __future__ import annotations

from pathlib import Path

import pandas as pd


def combine_matching(df1: pd.DataFrame, df2: pd.DataFrame, left_on: str, right_on: str, keep: bool) -> pd.DataFrame:
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


__all__ = ["combine_matching", "combine_fuels"]
