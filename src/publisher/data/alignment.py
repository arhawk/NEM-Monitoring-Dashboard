from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from .facility_metadata import load_facility_metadata_csv

_NAME_SUFFIXES = (
    "wind farm",
    "solar farm",
    "power station",
    "hydro power station",
    "remote generation",
    "pty ltd",
    "distribution network",
)

_SHORT_NAME_MAX_LEN = 8
_SHORT_NAME_MIN_SCORE = 0.85
_LONG_NAME_MIN_SCORE = 0.60

# Approximate AU state/territory bounding boxes (lat_min, lat_max, lng_min, lng_max).
# Checked in priority order when multiple regions match.
_STATE_BOUNDS: list[tuple[str, float, float, float, float]] = [
    ("ACT", -35.95, -35.12, 148.75, 149.45),
    ("TAS", -43.75, -39.15, 143.75, 148.35),
    ("WA", -35.25, -13.50, 112.85, 129.05),
    ("NT", -26.05, -10.90, 129.00, 138.05),
    ("SA", -38.15, -25.95, 128.95, 141.05),
    ("QLD", -29.25, -9.95, 137.95, 153.55),
    ("NSW", -37.55, -27.95, 140.95, 153.65),
    ("VIC", -39.25, -33.85, 140.85, 150.05),
]

_STATE_PRIORITY = ("ACT", "NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT")


def normalize_name(name: str | None) -> str:
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    text = str(name).lower().strip()
    for suffix in _NAME_SUFFIXES:
        text = re.sub(rf"\b{re.escape(suffix)}\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def infer_state_from_coords(lat: float | None, lng: float | None) -> str | None:
    if lat is None or lng is None:
        return None
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat_f) or not math.isfinite(lng_f):
        return None

    matches = [
        state
        for state, lat_min, lat_max, lng_min, lng_max in _STATE_BOUNDS
        if lat_min <= lat_f <= lat_max and lng_min <= lng_f <= lng_max
    ]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    for state in _STATE_PRIORITY:
        if state in matches:
            return state
    return matches[0]


def _token_jaccard(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(intersection) / len(union)


def score_name_similarity(oe_name: str, metadata_name: str) -> float:
    left = normalize_name(oe_name)
    right = normalize_name(metadata_name)
    if not left or not right:
        return 0.0
    sequence_score = SequenceMatcher(None, left, right).ratio()
    token_score = _token_jaccard(left, right)
    return max(sequence_score, token_score)


def _min_match_score(oe_name: str) -> float:
    normalized = normalize_name(oe_name)
    if len(normalized) < _SHORT_NAME_MAX_LEN:
        return _SHORT_NAME_MIN_SCORE
    return _LONG_NAME_MIN_SCORE


def find_nger_candidates(oe_row: pd.Series, nger_df: pd.DataFrame) -> pd.DataFrame:
    oe_name = oe_row.get("facility_name")
    if oe_name is None or (isinstance(oe_name, float) and math.isnan(oe_name)):
        return nger_df.iloc[0:0].copy()

    oe_text = str(oe_name).strip()
    if not oe_text:
        return nger_df.iloc[0:0].copy()

    normalized_oe = normalize_name(oe_text)
    substring_hits = nger_df[
        nger_df["facilityName"].str.contains(oe_text, case=False, na=False, regex=False)
    ]
    normalized_hits = (
        nger_df[nger_df["facilityName"].map(normalize_name) == normalized_oe]
        if normalized_oe
        else nger_df.iloc[0:0]
    )

    candidates = pd.concat([substring_hits, normalized_hits], ignore_index=True)
    if candidates.empty:
        return candidates
    return candidates.drop_duplicates(
        subset=["facilityName", "state", "primaryFuel"]
    ).reset_index(drop=True)


def find_cer_candidates(oe_row: pd.Series, cer_df: pd.DataFrame) -> pd.DataFrame:
    oe_name = oe_row.get("facility_name")
    if oe_name is None or (isinstance(oe_name, float) and math.isnan(oe_name)):
        return cer_df.iloc[0:0].copy()

    oe_text = str(oe_name).strip()
    if not oe_text:
        return cer_df.iloc[0:0].copy()

    normalized_oe = normalize_name(oe_text)
    substring_hits = cer_df[
        cer_df["powerStation"].str.contains(oe_text, case=False, na=False, regex=False)
    ]
    normalized_hits = (
        cer_df[cer_df["powerStation"].map(normalize_name) == normalized_oe]
        if normalized_oe
        else cer_df.iloc[0:0]
    )

    candidates = pd.concat([substring_hits, normalized_hits], ignore_index=True)
    if candidates.empty:
        return candidates
    return candidates.drop_duplicates(
        subset=["powerStation", "state", "fuelSource"]
    ).reset_index(drop=True)


def select_best_nger_match(
    oe_row: pd.Series, candidates: pd.DataFrame
) -> pd.Series | None:
    if candidates.empty:
        return None

    oe_name = str(oe_row.get("facility_name", ""))
    min_score = _min_match_score(oe_name)
    inferred_state = infer_state_from_coords(oe_row.get("lat"), oe_row.get("lng"))

    pool = candidates
    if inferred_state is not None:
        state_matches = candidates[candidates["state"] == inferred_state]
        if not state_matches.empty:
            pool = state_matches

    scored: list[tuple[float, pd.Series]] = []
    for _, candidate in pool.iterrows():
        score = score_name_similarity(oe_name, candidate["facilityName"])
        if score >= min_score:
            scored.append((score, candidate))

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def combine_fuels_from(
    nger_match: pd.Series | None, cer_candidates: pd.DataFrame
) -> list:
    fuels: list = []
    seen: set[str] = set()

    def append_fuel(value) -> None:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            fuels.append(text)

    if nger_match is not None and "primaryFuel" in nger_match.index:
        append_fuel(nger_match.get("primaryFuel"))

    if not cer_candidates.empty and "fuelSource" in cer_candidates.columns:
        for value in cer_candidates["fuelSource"]:
            append_fuel(value)

    return fuels


def build_facility_metadata(
    df1: pd.DataFrame, nger_df: pd.DataFrame, cer_df: pd.DataFrame
) -> pd.DataFrame:
    records: list[dict] = []
    for _, oe_row in df1.iterrows():
        nger_candidates = find_nger_candidates(oe_row, nger_df)
        best_nger = select_best_nger_match(oe_row, nger_candidates)
        cer_candidates = find_cer_candidates(oe_row, cer_df)

        if best_nger is not None:
            state = best_nger.get("state")
        else:
            state = infer_state_from_coords(oe_row.get("lat"), oe_row.get("lng"))

        records.append(
            {
                "facility_code": oe_row["facility_code"],
                "facility_name": oe_row["facility_name"],
                "lat": oe_row["lat"],
                "lng": oe_row["lng"],
                "state": state,
                "fuel_list": combine_fuels_from(best_nger, cer_candidates),
            }
        )

    grouped = pd.DataFrame.from_records(records)
    if grouped.empty:
        return grouped
    return grouped.drop_duplicates(subset=["facility_code"], keep="last").reset_index(
        drop=True
    )


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

    grouped = build_facility_metadata(df1, df2, df3)
    merged_df = pd.merge(df_cleaned, grouped, on="facility_code", how="inner")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(output_path, index=False)
    return merged_df


def get_state_bounds_map() -> dict[str, tuple[float, float, float, float]]:
    """Return state -> (lat_min, lat_max, lng_min, lng_max) bounding boxes."""
    return {
        state: (lat_min, lat_max, lng_min, lng_max)
        for state, lat_min, lat_max, lng_min, lng_max in _STATE_BOUNDS
    }


__all__ = [
    "build_facility_metadata",
    "build_publish_dataset",
    "combine_fuels",
    "combine_fuels_from",
    "combine_matching",
    "find_cer_candidates",
    "find_nger_candidates",
    "get_state_bounds_map",
    "infer_state_from_coords",
    "normalize_name",
    "score_name_similarity",
    "select_best_nger_match",
]
