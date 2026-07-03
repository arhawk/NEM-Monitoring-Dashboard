from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import pandas as pd

from .cache_store import load_cache, save_cache, cache_lock
from .client import create_session, fetch_facility_list, fetch_response
from .transform import fetch_data
from .paths import data_path


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

    all_merged_dfs: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_facility, f_code, date_start, date_end, cache): f_code
            for f_code in facility_list["facility_code"]
        }
        for future in as_completed(futures):
            f_code = futures[future]
            try:
                merged_df = future.result()
                if not merged_df.empty:
                    all_merged_dfs.append(merged_df)
            except Exception as e:
                print(f"Error processing facility {f_code}: {e}")

    consolidated_data = pd.concat(all_merged_dfs, ignore_index=True) if all_merged_dfs else pd.DataFrame()
    save_cache(cache)

    facility_list_path = data_path("facility_list.csv")
    consolidated_path = data_path("consolidated_data_total.csv")
    facility_list_path.parent.mkdir(parents=True, exist_ok=True)
    facility_list.to_csv(facility_list_path, index=False)
    consolidated_data.to_csv(consolidated_path, index=False)
    return facility_list, consolidated_data


__all__ = ["process_facility", "fetch_and_build_consolidated_data"]
