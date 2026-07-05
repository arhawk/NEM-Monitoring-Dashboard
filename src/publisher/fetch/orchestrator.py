from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.shared.paths import raw_data_path

from .cache import cache_lock, load_cache, save_cache
from .client import create_session, fetch_facility_list, fetch_response
from .transform import fetch_data


def process_facility(f_code: str, date_start: datetime, date_end: datetime, cache: dict[str, Any]) -> pd.DataFrame:
    """Process data for a single facility (thread-safe), using cache when possible."""
    print(f"Processing facility: {f_code}")
    data_sources = {
        "facility": {
            "api_url": "https://api.openelectricity.org.au/v4/data/facilities/NEM",
            "metrics": ["power", "emissions"],
        },
        "market": {
            "api_url": "https://api.openelectricity.org.au/v4/market/network/NEM",
            "metrics": ["price", "demand"],
        },
    }

    source_data: dict[str, pd.DataFrame] = {}
    session = create_session()

    try:
        for source_type, config in data_sources.items():
            cache_key = f"{source_type}|{f_code}|{date_start.isoformat()}|{date_end.isoformat()}"

            if cache_key in cache:
                source_data[source_type] = cache[cache_key]["consolidated_data"]
                continue

            params = {
                "facility_code": f_code,
                "metrics": config["metrics"],
                "interval": "5m",
                "date_start": date_start,
                "date_end": date_end,
            }
            response = fetch_response(session, config["api_url"], params)
            source_df = fetch_data(response, f_code)

            if not source_df.empty:
                with cache_lock:
                    cache[cache_key] = {
                        "date_start": date_start,
                        "date_end": date_end,
                        "consolidated_data": source_df,
                    }

            source_data[source_type] = source_df

        facility_df = source_data["facility"]
        market_df = source_data["market"]

        if not facility_df.empty and not market_df.empty:
            merged_df = pd.merge(facility_df, market_df, on=["timestamp", "facility_code"], how="outer")
        elif not facility_df.empty:
            merged_df = facility_df
        elif not market_df.empty:
            merged_df = market_df
        else:
            merged_df = pd.DataFrame()

        return merged_df
    finally:
        session.close()


def _write_raw_artifacts(
    facility_list: pd.DataFrame,
    consolidated_data: pd.DataFrame,
    facility_list_path: Path,
    consolidated_path: Path,
) -> None:
    facility_list_path.parent.mkdir(parents=True, exist_ok=True)
    facility_list.to_csv(facility_list_path, index=False)
    consolidated_data.to_csv(consolidated_path, index=False)


def fetch_and_build_consolidated_data(
    *,
    date_start: datetime,
    date_end: datetime,
    max_workers: int = 15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch all facility data and persist the raw artifacts."""
    cache = load_cache()
    facility_list = fetch_facility_list()
    if facility_list.empty:
        return facility_list, pd.DataFrame()

    facility_list_path = raw_data_path("open_electricity", "facility_list.csv")
    consolidated_path = raw_data_path("open_electricity", "consolidated_data_total.csv")
    _write_raw_artifacts(facility_list, pd.DataFrame(), facility_list_path, consolidated_path)

    all_merged_dfs: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_facility, f_code, date_start, date_end, cache): f_code
            for f_code in facility_list["facility_code"]
        }
        total_facilities = len(futures)
        completed_facilities = 0
        for future in as_completed(futures):
            f_code = futures[future]
            try:
                merged_df = future.result()
                if not merged_df.empty:
                    all_merged_dfs.append(merged_df)
                    consolidated_data = pd.concat(all_merged_dfs, ignore_index=True)
                    _write_raw_artifacts(facility_list, consolidated_data, facility_list_path, consolidated_path)
                completed_facilities += 1
                print(f"[Publisher] Completed {completed_facilities}/{total_facilities}: {f_code}")
            except Exception as e:
                print(f"Error processing facility {f_code}: {e}")

    consolidated_data = pd.concat(all_merged_dfs, ignore_index=True) if all_merged_dfs else pd.DataFrame()
    save_cache(cache)
    _write_raw_artifacts(facility_list, consolidated_data, facility_list_path, consolidated_path)
    return facility_list, consolidated_data


__all__ = ["process_facility", "fetch_and_build_consolidated_data"]
