from __future__ import annotations

from pathlib import Path

import pandas as pd

from .matching import combine_fuels, combine_matching


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
    df2 = pd.read_csv(nger_path)
    df3 = pd.read_csv(cer_path)

    tmp_df = combine_matching(df1, df2, left_on="facility_name", right_on="facilityName", keep=False)
    tmp_df2 = combine_matching(tmp_df, df3, left_on="facility_name", right_on="powerStation", keep=True)
    tmp_df3 = tmp_df2[["facility_code", "facility_name", "primaryFuel", "state_x", "lat", "lng", "fuelSource"]]
    tmp_df3 = tmp_df3.rename(columns={"state_x": "state", "fuelSource": "futureFuelSource"})
    tmp_df3_clean = tmp_df3.drop_duplicates()

    grouped = (
        tmp_df3_clean.groupby(["facility_name", "facility_code", "lat", "lng", "state"])
        .apply(lambda x: combine_fuels(x))
        .reset_index(name="fuel_list")
    )

    merged_df = pd.merge(df_cleaned, grouped, on="facility_code", how="inner")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(output_path, index=False)
    return merged_df


__all__ = ["combine_matching", "combine_fuels", "build_publish_dataset"]
